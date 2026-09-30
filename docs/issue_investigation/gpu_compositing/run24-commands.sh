#!/bin/sh
# Run 24 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Line 8434 was BLOCKED outright by guard.sh (a `2>/dev/null` on an ssh probe to the board, flagged by the project's own hook) and never ran at all; line 8446 is the identical command with that redirection removed, and it DID run (background task b1lgo9rvu), producing motion-linear-shrunk-raw.txt. Picked because the guard-blocked attempt could not have produced anything -- not a close call.

# --- main transcript line 8434  2026-09-22T17:50:07Z --- REJECTED by guard.sh (2>/dev/null on an ssh probe), never ran ---

# --- main line 8434  2026-09-22T17:50:07.975Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p12_motion.js 240 > motion-linear-shrunk-raw.txt 2>&1
echo "EXIT=$?"
# confirm the new bundle loaded
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -c "grep -rhoE \"index-[A-Za-z0-9_]+\\.js\" /home/root/.surf/cache 2>/dev/null | sort -u"'
grep -aoE 'KP2\|[^"]*' motion-linear-shrunk-raw.txt | tail -1 | cut -c1-90

# --- main transcript line 8446  2026-09-22T17:50:23Z --- retry without the suppression, SUCCEEDED (background task b1lgo9rvu) ---

# --- main line 8446  2026-09-22T17:50:23.257Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p12_motion.js 240 > motion-linear-shrunk-raw.txt 2>&1
echo "EXIT=$?"; grep -aoE 'KP2\|[^"]*' motion-linear-shrunk-raw.txt | tail -1 | cut -c1-90

# --- main line 8454  2026-09-22T17:54:35.521Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
# confirm new bundle loaded (no stderr suppression)
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'grep -rhoE "index-[A-Za-z0-9_]+\.js" /home/root/.surf/cache | sort -u'
echo "=== step-size comparison (px moved per frame) ==="
python3 - <<'PY'
import parse_motion as pm
for f,tag in [('motion-720p-cv-raw.txt','OLD ease-in-out, V=25, 35% move'),
              ('motion-linear-shrunk-raw.txt','NEW linear, V=15, 84% move')]:
    txt=open(f).read().replace(chr(34),'')
    d=pm.parse([l for l in txt.splitlines() if 'KP2|' in l][-1])
    tot=sum(c for c,_ in d['pbuckets']) or 1
    b=d['pbuckets']
    static=b[0][0]
    lbls=['~0','.02-.5','.5-1','1-2','2-4','4-8','>8']
    print(f"\n{tag}:")
    print("  "+"  ".join(f"{l}:{100*c/tot:.0f}%" for l,(c,_) in zip(lbls,b)))
    rtot=sum(c for c,_ in d['rbuckets']) or 1
    print(f"  static(0-rows) {100*d['rbuckets'][0][0]/rtot:.0f}% of frames  |  overall ~{pm.fps(d['avg']):.0f}fps")
PY
