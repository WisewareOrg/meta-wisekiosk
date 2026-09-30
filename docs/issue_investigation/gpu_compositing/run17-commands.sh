#!/bin/sh
# Run 17 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# The line-7212 deploy used the pre-parameterised run-phase.sh, whose OWN readback (`grep 'KP|'`) cannot match this probe's `KP2|` payload -- so its capture (during-motion-raw.txt, uncatalogued) is empty, but the `cat > script.js` half of that command did land the probe, which kept accumulating for ~27 minutes until a standalone xprop poll at line 7417 read it out at the '1630' second mark -- and that payload is byte-for-byte the one committed as motion-baseline-raw.txt. Picked on that exact string match, not by proximity.

# --- main transcript line 7212  2026-09-22T14:03:22Z --- old run-phase.sh (2-arg, HOST hardcoded);
# its OWN readback used grep 'KP|' which cannot match this probe's 'KP2|' payload, so its own
# capture (during-motion-raw.txt) is empty/unusable -- but the `cat > script.js` deploy half DID
# land the probe on the board, and it kept accumulating state until read out at line 7417.

# --- main line 7212  2026-09-22T14:03:22.431Z ---
/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/run-phase.sh /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p12_motion.js 240 2>&1 | tee /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/during-motion-raw.txt

# --- main line 7365  2026-09-22T14:28:03.318Z  (Write) ---
cat > run-phase-motion.sh <<'PROBE_EOF'
#!/usr/bin/env bash
# Deploy the MOVING-vs-STATIC probe (p12_motion.js) to the prod kiosk, restart onto
# a cleared cache, let it run, then read the KP2| payload back out of the X title.
#
#   run-phase-motion.sh root@<host> <probe.js> <seconds>
#
# The sibling run-phase.sh reads the probe4 family's KP| payload. This one reads the
# KP2| payload the motion probe emits -- a different, longer wire shape (one record
# per 20 s block), so it greps KP2| and reads a larger title window. The board is
# named on the command line; this repository is public and carries no device address.
#
# Recoverable over the wire: the only device state touched is ~/.surf/script.js and
# the WebKit cache, both restored by deploying a zero-byte script.js and restarting.
set -uo pipefail

HOST=${1:?usage: run-phase-motion.sh root@<host> <probe.js> <seconds>}
PROBE=${2:?usage: run-phase-motion.sh root@<host> <probe.js> <seconds>}
SECS=${3:?usage: run-phase-motion.sh root@<host> <probe.js> <seconds>}
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)

"$REPO/tools/kiosk-ssh.sh" "$HOST" 'cat > /home/root/.surf/script.js' < "$PROBE" || exit 1

"$REPO/tools/kiosk-ssh.sh" "$HOST" "sh -s" <<EOF
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep $SECS
export DISPLAY=:0
for id in \$(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print \$1}'); do
  xprop -len 32000 -id \$id WM_NAME 2>/dev/null | grep 'KP2|'
done
echo "LOAD \$(cat /proc/loadavg)"
p=\$(pidof WebKitWebProcess | cut -d' ' -f1)
[ -n "\$p" ] && grep VmRSS /proc/\$p/status
EOF

PROBE_EOF

# --- main line 7378  2026-09-22T14:28:32.562Z  (Write) ---
cat > parse_motion.py <<'PROBE_EOF'
#!/usr/bin/env python3
"""Render the MOVING-vs-STATIC probe's KP2| window-title payload as a report.

The motion probe (p12_motion.js) tags every rAF frame by how many marquee rows
actually moved that frame and buckets frame time three ways per 20 s block:
all frames, MOVING frames, STATIC frames. The during-MOTION frame time -- the
number the whole investigation is missing -- is the MOVING mean inside a T block.

A payload is only trusted when it LANDED: KP2| present, at least one marquee row
seen (M<n>/<n>, n>0), and at least one T block with moving frames. A capture with
no marquee rows or no moving frames measured nothing and is reported UNMEASURED,
never as a null. Proven against synthetic landed and did-not-land payloads in
parse_motion_test.py before use.
"""
import re
import sys

PAT = (r"KP2\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|M(\d+)/(\d+)"
       r"\|R([\d.:]*)\|P([\d.:]*)\|B(.*)")


def pairs(s):
    """'2:45.3:60' -> [(2,45),(3,60)] (count, meanMs)."""
    out = []
    for e in filter(None, s.split(".")):
        c, _, m = e.partition(":")
        out.append((int(c), int(m or 0)))
    return out


def blocks(s):
    """One record per 20 s block: i,ty,n,meanAll,mn,meanMoving,sn,meanStatic,px."""
    out = []
    for e in filter(None, s.split(";")):
        f = e.split(",")
        if len(f) != 8:
            continue
        head = f[0]                       # e.g. "12T"
        ty = head[-1]
        idx = int(head[:-1])
        out.append(dict(i=idx, ty=ty, n=int(f[1]), mean=int(f[2]),
                        mn=int(f[3]), mmov=int(f[4]),
                        sn=int(f[5]), mstat=int(f[6]), px=int(f[7])))
    return out


def parse(title):
    m = re.search(PAT, title)
    if not m:
        return None
    g = m.groups()
    return dict(sec=int(g[0]), frames=int(g[1]), avg=int(g[2]), max=int(g[3]),
                marquee=int(g[4]), rows=int(g[5]),
                rbuckets=pairs(g[6]), pbuckets=pairs(g[7]), blocks=blocks(g[8]))


def fps(ms):
    return 1000.0 / ms if ms else 0.0


def validate(d):
    """Return (ok, reason). A payload that measured no motion is not a null."""
    if d["marquee"] == 0:
        return False, f"no marquee rows seen (M{d['marquee']}/{d['rows']})"
    tblocks = [b for b in d["blocks"] if b["ty"] == "T" and b["i"] > 0]
    if not tblocks:
        return False, "no T (transform-reading) blocks after block 0"
    if not any(b["mn"] > 0 for b in tblocks):
        return False, "no moving frames captured in any T block"
    return True, "landed"


def report(d, label):
    ok, reason = validate(d)
    print(f"===== {label} =====")
    print(f"window {d['sec']}s  frames {d['frames']}  overall mean {d['avg']}ms "
          f"max {d['max']}ms  ~{fps(d['avg']):.1f} fps")
    print(f"marquee rows seen {d['marquee']} of {d['rows']} ride rows")
    if not ok:
        print(f"\n*** UNMEASURED: {reason} -- do NOT read this as a null ***")
        return False

    # Per-block MOVING vs STATIC. Compare only inside one block.
    print("\nper 20s block  (compare MOVING vs STATIC only within a row):")
    print(f"  {'blk':>4}  {'all':>10}  {'MOVING':>16}  {'static':>16}  {'px':>7}")
    mov_ms, mov_n = 0, 0
    for b in d["blocks"]:
        allc = f"{b['n']:4d}f {b['mean']:4d}ms"
        if b["ty"] == "T":
            movc = f"{b['mn']:4d}f {b['mmov']:4d}ms {fps(b['mmov']):4.1f}fps"
            stac = f"{b['sn']:4d}f {b['mstat']:4d}ms {fps(b['mstat']):4.1f}fps"
            if b["i"] > 0 and b["mn"] > 0:
                mov_ms += b["mmov"] * b["mn"]
                mov_n += b["mn"]
        else:
            movc = stac = "  (N: no read)"
        print(f"  {b['i']:>2}{b['ty']}  {allc:>10}  {movc:>16}  {stac:>16}  {b['px']:7d}")

    if mov_n:
        agg = mov_ms / mov_n
        print(f"\nDURING-MOTION (frame-weighted over T blocks, block 0 discarded):")
        print(f"  {mov_n} moving frames, mean {agg:.0f}ms  ~{fps(agg):.2f} fps")

    print("\nframes bucketed by rows moving that frame  (count:meanMs):")
    for i, (c, ms) in enumerate(d["rbuckets"]):
        if c:
            print(f"  {i} rows moving  {c:6d} frames  {ms:5d}ms  ~{fps(ms):4.1f} fps")
    return True


if __name__ == "__main__":
    text = open(sys.argv[1]).read().replace(chr(34), "")
    lines = [l for l in text.splitlines() if "KP2|" in l]
    if not lines:
        sys.exit("no KP2| payload in " + sys.argv[1])
    d = parse(lines[-1])
    if not d:
        sys.exit("payload did not match:\n" + lines[-1][:400])
    report(d, sys.argv[2] if len(sys.argv) > 2 else sys.argv[1])

PROBE_EOF

# --- main line 7391  2026-09-22T14:29:07.899Z  (Write) ---
cat > parse_motion_test.py <<'PROBE_EOF'
#!/usr/bin/env python3
"""Prove parse_motion reports BOTH outcomes before any board number is trusted.

A discriminator that cannot come out both ways discriminates nothing. Three
synthetic KP2| payloads exercise the landed case and the two did-not-land cases
(no marquee rows; marquee rows but zero moving frames). Run: python3 parse_motion_test.py
"""
import parse_motion as pm

# --- Landed: marquee rows seen, T blocks with moving frames, motion slower than static
LANDED = (
    'KP2|500|f8000|av90|mx1200|M6/20'
    '|R3000:38.600:95.500:140.300:200.200:260.0:0.0:0.0:0.0:0'
    '|P3000:38.900:120.600:180.300:240.100:300.0:0.0:0'
    '|B0T,700,45,300,84,400,20,12000;1T,650,90,250,180,400,35,9000;'
    '2T,640,88,240,175,400,34,8800;3N,600,42,0,0,0,0,0;'
    '4T,660,86,255,170,405,33,9100'
)

# --- Did not land: no marquee rows on the page (M0/20)
NO_ROWS = (
    'KP2|500|f8000|av40|mx900|M0/20'
    '|R8000:40.0:0.0:0.0:0.0:0.0:0.0:0.0:0.0:0'
    '|P8000:40.0:0.0:0.0:0.0:0.0:0.0:0'
    '|B0T,700,40,0,0,700,40,0;1T,650,40,0,0,650,40,0;3N,600,42,0,0,0,0,0'
)

# --- Did not land: rows present but nothing ever moved (animation not running)
NO_MOTION = (
    'KP2|500|f8000|av44|mx900|M6/20'
    '|R8000:44.0:0.0:0.0:0.0:0.0:0.0:0.0:0.0:0'
    '|P8000:44.0:0.0:0.0:0.0:0.0:0.0:0'
    '|B0T,700,44,0,0,700,44,0;1T,650,44,0,0,650,44,0;3N,600,42,0,0,0,0,0'
)

fails = 0


def check(name, payload, want_ok, want_reason_sub=None):
    global fails
    d = pm.parse(payload)
    assert d is not None, f"{name}: payload did not parse at all"
    ok, reason = pm.validate(d)
    status = "PASS" if ok == want_ok else "FAIL"
    if ok != want_ok:
        fails += 1
    print(f"[{status}] {name}: validate -> ok={ok} ({reason})")
    if want_reason_sub and want_reason_sub not in reason:
        fails += 1
        print(f"       FAIL: expected reason to mention {want_reason_sub!r}")


check("LANDED", LANDED, True)
check("NO_ROWS", NO_ROWS, False, "no marquee rows")
check("NO_MOTION", NO_MOTION, False, "no moving frames")

# Sanity: the landed payload's during-motion fps is well below its overall mean.
d = pm.parse(LANDED)
tblocks = [b for b in d["blocks"] if b["ty"] == "T" and b["i"] > 0 and b["mn"] > 0]
mov_ms = sum(b["mmov"] * b["mn"] for b in tblocks) / sum(b["mn"] for b in tblocks)
mov_fps = pm.fps(mov_ms)
overall_fps = pm.fps(d["avg"])
print(f"\nLANDED during-motion mean {mov_ms:.0f}ms (~{mov_fps:.2f} fps) "
      f"vs overall ~{overall_fps:.1f} fps")
if not (mov_fps < overall_fps):
    fails += 1
    print("       FAIL: during-motion fps should be below the overall mean")

print("\n--- full report on the LANDED payload ---")
pm.report(d, "LANDED sample")

print()
if fails:
    raise SystemExit(f"{fails} check(s) FAILED")
print("all checks passed")

PROBE_EOF

# --- main line 7401  2026-09-22T14:29:58.445Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "== uptime =="; uptime
echo "== buildinfo =="; grep ^meta-wisekiosk /etc/buildinfo 2>/dev/null
echo "== kiosk.conf =="; cat /data/config/kiosk.conf 2>/dev/null
echo "== loaded bundle(s) =="; ls -1 /home/root/.surf/cache/WebKitCache/Version*/ 2>/dev/null | grep -o 'index-[A-Za-z0-9_]*\.js' | sort -u
echo "== surf script bytes =="; wc -c /home/root/.surf/script.js 2>/dev/null
EOF

# --- main line 7412  2026-09-22T14:30:39.081Z ---
cp /home/tjwise/.claude/deliverables/9253304a-ddb2-4c2c-827e-a05b0942ac7b/p12_motion.js \
   /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing/p12_motion.js
wc -c /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing/p12_motion.js
chmod +x /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing/run-phase-motion.sh

# --- main line 7417  2026-09-22T14:30:49.967Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  xprop -len 32000 -id $id WM_NAME 2>/dev/null | grep 'KP2|'
done
EOF

# --- main line 7430  2026-09-22T14:32:32.795Z ---
cat > /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing/motion-baseline-raw.txt <<'EOF'
WM_NAME(STRING) = "@cgDISMfxT:- | KP2|1630|f20337|av80|mx2013|M5/20|R9658:44.2200:94.714:143.1711:157.765:177.374:197.65:216.3:327.0:0|P9658:44.766:87.442:75.1034:73.554:114.583:126.2453:199|B0T,230,87,69,120,161,72,1338;1T,303,66,89,113,214,46,1960;2T,273,73,79,119,194,54,1964;3N,280,71,0,0,0,0,0;4T,243,84,84,121,159,64,2322;5T,283,70,78,142,205,43,1792;6T,276,73,103,100,173,57,1992;7N,232,86,0,0,0,0,0;8T,306,64,89,107,217,47,2214;9T,241,84,105,127,136,51,2012;10T,279,72,91,120,188,49,2142;11N,304,66,0,0,0,0,0;12T,280,71,101,113,179,47,2313;13T,220,92,94,135,126,59,1891;14T,282,70,82,146,200,39,2046;15N,190,106,0,0,0,0,0;16T,306,66,117,107,189,40,2189;17T,252,78,103,136,149,38,2336;18T,260,78,110,136,150,35,2432;19N,225,88,0,0,0,0,0;20T,234,87,116,134,118,40,2869;21T,182,108,134,125,48,60,2246;22T,233,87,118,118,115,55,2292;23N,195,102,0,0,0,0,0;24T,240,84,114,122,126,49,2693;25T,186,108,103,155,83,50,2628;26T,216,93,115,129,101,51,2335;27N,173,114,0,0,0,0,0;28T,224,90,104,133,120,53,2786;29T,170,117,82,174,88,65,2377"
EOF
echo "saved $(wc -c < /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing/motion-baseline-raw.txt) bytes"

# --- main line 7443  2026-09-22T14:32:41.966Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing && python3 parse_motion.py motion-baseline-raw.txt "PROD baseline (7ce44ba, compositing off, demo data)"
