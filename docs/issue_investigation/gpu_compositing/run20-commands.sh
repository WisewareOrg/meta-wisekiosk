#!/bin/sh
# Run 20 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Single deploy+capture via run-phase-motion.sh (p16_duration.js -> duration-cv179-raw.txt), no retries found.

# --- main line 7796  2026-09-22T15:28:21.126Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p16_duration.js 450 > duration-cv179-raw.txt 2>&1
echo "EXIT=$?"; grep -aoE 'KP3\|[^"]*' duration-cv179-raw.txt | tail -1 | cut -c1-140

# --- main line 7820  2026-09-22T15:35:58.200Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 parse_duration.py duration-cv179-raw.txt "constant-velocity V=179 vs fixed-8s, prod 7ce44ba" 2>&1 | sed -n '1,4p;/BY ARM/,$p' | head -40
