#!/bin/sh
# Run 18 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Covers both 18a (steps-k40-raw.txt) and 18b (steps-k10-raw.txt) via `run-phase-motion.sh`, each a single clean pass, no retries found.

# --- main line 7537  2026-09-22T14:45:16.424Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p13_steps.js 450 > /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing/steps-k40-raw.txt 2>&1
echo "EXIT=$?"
echo "---- tail ----"
tail -5 steps-k40-raw.txt | cut -c1-200

# --- main line 7546  2026-09-22T14:53:02.523Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
echo "==== raw tail (payload + load/rss) ===="
grep -aoE 'KP3\|[^"]*' steps-k40-raw.txt | tail -1 | cut -c1-260
echo
grep -aE 'LOAD|VmRSS' steps-k40-raw.txt
echo "==== parsed ===="
python3 parse_steps.py steps-k40-raw.txt "steps(K=40) vs baseline, prod 7ce44ba"

# --- main line 7573  2026-09-22T14:55:41.853Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p13_steps.js 450 > steps-k10-raw.txt 2>&1
echo "EXIT=$?"; tail -2 steps-k10-raw.txt | cut -c1-120

# --- main line 7613  2026-09-22T15:04:13.569Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
rm -f p14_fontscale.js && echo "removed p14_fontscale.js (font-size lever disallowed)"
echo "==== K=10 capture state ===="
if grep -aq 'KP3|' steps-k10-raw.txt 2>/dev/null; then
  echo "K=10 capture COMPLETE — board free"
  grep -aE 'LOAD|VmRSS|EXIT' steps-k10-raw.txt
else
  echo "K=10 still running or no payload yet:"; tail -3 steps-k10-raw.txt 2>/dev/null | cut -c1-120
fi

# --- main line 7626  2026-09-22T15:04:19.326Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 parse_steps.py steps-k10-raw.txt "steps(K=10) vs baseline, prod 7ce44ba" 2>&1 | sed -n '1,6p;/BY ARM/,/SCORE/p'
