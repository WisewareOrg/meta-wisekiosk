#!/bin/sh
# Run 30 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the named /tmp/kc.txt mapping (line 9485).


# --- transcript line 9167  2026-09-22T21:07:14.617Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p22_contain.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 300
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 12000 -id $id WM_NAME 2>/dev/null | grep 'KC|')
  [ -n "$t" ] && echo "$t"
done
true
EOF


# --- transcript line 9182  2026-09-22T21:12:24.705Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aoE 'KC\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b29y9gz25.output | tail -1 > /tmp/kc.txt
cat /tmp/kc.txt | cut -c1-160; echo
python3 parse_contain.py /tmp/kc.txt 0.04 "contain:paint on cards" 2>&1 | sed -n '1,22p'


# --- transcript line 9187  2026-09-22T21:15:35.454Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -c ": > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk"'
sleep 24; tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1
