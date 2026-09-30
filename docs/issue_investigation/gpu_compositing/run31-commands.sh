#!/bin/sh
# Run 31 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the named /tmp/fz.txt mapping (line 9485).


# --- transcript line 9214  2026-09-22T21:25:09.150Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p23_freeze.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 205
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 12000 -id $id WM_NAME 2>/dev/null | grep 'FZ|')
  [ -n "$t" ] && echo "$t"
done
true
EOF


# --- transcript line 9222  2026-09-22T21:28:41.500Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aoE 'FZ\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bng0xllp7.output | tail -1 > /tmp/fz.txt
cat /tmp/fz.txt | cut -c1-160; echo
python3 parse_freeze.py /tmp/fz.txt 0.04 "page frozen" 2>&1 | sed -n '1,20p'


# --- transcript line 9234  2026-09-22T21:32:06.170Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -c ": > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk"'
sleep 24; tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1
