#!/bin/sh
# Run 25 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Single deploy+capture via run-phase-motion.sh (p18_scroll.js -> scroll-vs-transform-raw.txt), no retries found.

# --- main line 8501  2026-09-22T18:32:45.373Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p18_scroll.js 450 > scroll-vs-transform-raw.txt 2>&1
echo "EXIT=$?"; grep -aoE 'KP18\|[^"]*' scroll-vs-transform-raw.txt | tail -1 | cut -c1-110

# --- main line 8516  2026-09-22T18:40:23.544Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 parse_scroll.py scroll-vs-transform-raw.txt "scroll vs transform, prod 720p" 2>&1 | sed -n '1,40p'
