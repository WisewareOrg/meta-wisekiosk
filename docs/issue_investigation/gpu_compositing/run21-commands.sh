#!/bin/sh
# Run 21 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Single deploy+capture via run-phase-motion.sh (p17_paintcost.js -> paintcost-raw.txt), no retries found.

# --- main line 7877  2026-09-22T15:49:28.782Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p17_paintcost.js 450 > paintcost-raw.txt 2>&1
echo "EXIT=$?"; grep -aoE 'KP3\|[^"]*' paintcost-raw.txt | tail -1 | cut -c1-120

# --- main line 7885  2026-09-22T15:57:05.708Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 parse_steps.py paintcost-raw.txt "PAINT-COST: text (A) vs solid fill (B), prod 7ce44ba" 2>&1 | sed -n '1,4p;/BY ARM/,/SCORE/p'
