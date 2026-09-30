#!/bin/sh
# Run 23 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Single deploy+capture via run-phase-motion.sh (p12_motion.js, constant-velocity marquee, 240s -> motion-720p-cv-raw.txt), no retries found.

# --- main line 8304  2026-09-22T17:16:58.815Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p12_motion.js 240 > motion-720p-cv-raw.txt 2>&1
echo "EXIT=$?"; grep -aoE 'KP2\|[^"]*' motion-720p-cv-raw.txt | tail -1 | cut -c1-150

# --- main line 8312  2026-09-22T17:21:06.384Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 parse_motion.py motion-720p-cv-raw.txt "720p + CV marquee, prod" 2>&1 | sed -n '1,4p;/DURING-MOTION/,/7 rows/p'

# --- main line 8317  2026-09-22T17:22:59.715Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 - <<'PY'
import parse_motion as pm
d=pm.parse(open('motion-720p-cv-raw.txt').read().replace(chr(34),'').splitlines()[-1])
PXE=['0','0-0.5','0.5-1','1-2','2-4','4-8','>8']
print("px-moved-per-frame histogram (jump = frames in the >8px bucket):")
for lbl,(c,ms) in zip(PXE,d['pbuckets']):
    if c: print(f"  {lbl:>7} px/frame : {c:6d} frames   {ms:4d}ms mean")
print(f"\noverall max single frame: {d['max']}ms")
PY

# --- main line 8327  2026-09-22T17:23:15.851Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 - <<'PY'
import parse_motion as pm
txt=open('motion-720p-cv-raw.txt').read().replace(chr(34),'')
line=[l for l in txt.splitlines() if 'KP2|' in l][-1]
d=pm.parse(line)
PXE=['~0','0.02-0.5','0.5-1','1-2','2-4','4-8','>8']
tot=sum(c for c,_ in d['pbuckets']) or 1
print("px-moved-per-frame (sum over moving rows); a marquee JUMP shows as the >8 bucket:")
for lbl,(c,ms) in zip(PXE,d['pbuckets']):
    print(f"  {lbl:>9} px : {c:6d} frames ({100*c/tot:4.1f}%)  {ms:4d}ms mean")
print(f"\nmax single frame: {d['max']}ms")
PY

# --- main line 8333  2026-09-22T17:23:38.795Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 - <<'PY'
import parse_motion as pm
for f,tag in [('motion-720p-raw.txt','720p, ORIGINAL marquee (no CV/sync)'),
              ('motion-720p-cv-raw.txt','720p + my CV/sync marquee')]:
    txt=open(f).read().replace(chr(34),'')
    line=[l for l in txt.splitlines() if 'KP2|' in l][-1]
    d=pm.parse(line)
    tot=sum(c for c,_ in d['pbuckets']) or 1
    over8=d['pbuckets'][6][0]
    print(f"{tag}: >8px-jump frames = {over8} ({100*over8/tot:.1f}%), max frame {d['max']}ms")
PY
