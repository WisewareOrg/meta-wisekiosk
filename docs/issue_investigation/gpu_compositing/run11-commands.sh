#!/bin/sh
# Run 11 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: subagent agent-adeb77092a2242020.jsonl
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Single deploy+capture (p6_title.js -> title-cadence-raw.txt), no retries found.

# --- adeb77092a2242020 line 349  2026-09-22T12:29:06.748Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < "$SP/p6_title.js"
echo "write-rc=$?"
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'wc -c < /home/root/.surf/script.js'
wc -c < "$SP/p6_title.js"

# --- adeb77092a2242020 line 351  2026-09-22T12:29:14.392Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
timeout 560 /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' > "$SP/title-cadence-raw.txt" 2>&1 <<'EOF'
systemctl restart kiosk
sleep 400
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  xprop -len 8000 -id $id WM_NAME 2>/dev/null | grep 'KP|'
done
echo "LOAD $(cat /proc/loadavg)"
p=$(pidof WebKitWebProcess | cut -d' ' -f1)
[ -n "$p" ] && grep VmRSS /proc/$p/status
EOF
echo "capture-rc=$?"
wc -c < "$SP/title-cadence-raw.txt"

# --- adeb77092a2242020 line 355  2026-09-22T12:29:39.272Z ---
cat > /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/parse_title.py <<'PY'
#!/usr/bin/env python3
"""Interleaved title-write-cadence arms: does frames>250ms track the exfil poke rate?"""
import re, sys
import parse4

A = r'f(\d+):b(\d+):tw(\d+):m(\d+)'
PAT = r'KA\|arm(-?\d+)\|FAST1_' + A + r'\|SLOW_' + A + r'\|FAST2_' + A

txt = open(sys.argv[1]).read().replace('"', '')
lines = [l for l in txt.splitlines() if 'KA|' in l]
if not lines:
    sys.exit("no KA| payload in " + sys.argv[1])
m = re.search(PAT, lines[-1])
if not m:
    sys.exit("KA| did not match:\n" + lines[-1][:300])
g = [int(x) for x in m.groups()]
arms = [g[1:5], g[5:9], g[9:13]]
names = ["FAST1 (title 1000ms)", "SLOW  (title 4000ms)", "FAST2 (title 1000ms)"]
want_tw = [120, 30, 120]          # 120 s arms at 1/s, 0.25/s, 1/s
DUR = 120.0

print(f"{'arm':<24}{'frames':>8}{'>250ms':>8}{'big/s':>8}{'titlewrites':>13}{'tw/s':>7}{'mean':>7}")
for n, a, w in zip(names, arms, want_tw):
    f, b, tw, mean = a
    print(f"{n:<24}{f:>8}{b:>8}{b/DUR:>8.2f}{tw:>13}{tw/DUR:>7.2f}{mean:>6}ms")

print("\ncadence landing check (did the arm's write rate actually change?):")
ok = True
for n, a, w in zip(names, arms, want_tw):
    tw = a[2]
    good = abs(tw - w) <= max(6, 0.15 * w)
    ok &= good
    print(f"  {n:<24} wrote {tw:>4} titles, expected ~{w:<4} -> {'OK' if good else '*** MISMATCH ***'}")
if not ok:
    print("  *** CADENCE DID NOT APPLY AS INTENDED -- treat arms as UNMEASURED ***")

# drift control: interpolate the two FAST arms to the SLOW arm's midpoint
f1, sl, f2 = arms[0][1] / DUR, arms[1][1] / DUR, arms[2][1] / DUR
pred = f1 + (f2 - f1) * 0.5
tw_ratio = (arms[0][2] + arms[2][2]) / 2.0 / max(arms[1][2], 1)
print(f"\ndrift control: FAST1={f1:.2f}/s FAST2={f2:.2f}/s -> predicted at SLOW midpoint {pred:.2f}/s")
print(f"               SLOW measured {sl:.2f}/s   (delta {sl-pred:+.2f}/s, {100*(sl-pred)/pred:+.0f}%)")
print(f"\ntitle-write rate ratio FAST:SLOW = {tw_ratio:.1f}x")
print(f"big-frame rate ratio   FAST:SLOW = {pred/max(sl,1e-9):.2f}x")
print("\nIf the floor were the exfil artifact, the two ratios would match "
      f"(~{tw_ratio:.0f}x). If independent, the big-frame ratio is ~1.0x.")

d = parse4.parse(lines[-1])
if d:
    print(f"\nwhole run: {d['sec']}s {d['frames']} frames mean {d['avg']}ms M{d['marquee']}/{d['rows']} "
          f"ROT{d['rotn']} big {d['bigtot']} ({d['bigtot']/max(d['sec'],1):.2f}/s)")
PY
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
real=$(grep -o 'KP|.*' hang-after-raw.txt)
echo "######## SYNTHETIC: floor IS the artifact (big tracks tw) ########"
echo "WM_NAME(STRING) = \"KA|arm2|FAST1_f1800:b240:tw120:m66|SLOW_f1900:b60:tw30:m52|FAST2_f1790:b245:tw120:m67|${real}\"" > /tmp/claude-1000/syn-art.txt
python3 parse_title.py /tmp/claude-1000/syn-art.txt
echo
echo "######## SYNTHETIC: floor INDEPENDENT of tw ########"
echo "WM_NAME(STRING) = \"KA|arm2|FAST1_f1800:b120:tw120:m66|SLOW_f1900:b128:tw30:m66|FAST2_f1790:b130:tw120:m67|${real}\"" > /tmp/claude-1000/syn-ind.txt
python3 parse_title.py /tmp/claude-1000/syn-ind.txt

# --- adeb77092a2242020 line 359  2026-09-22T12:30:02.364Z ---
f=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/title-cadence-raw.txt
until grep -q 'LOAD ' "$f" 2>/dev/null; do sleep 15; done
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
python3 parse_title.py title-cadence-raw.txt
grep -E 'LOAD|VmRSS' title-cadence-raw.txt
