#!/bin/sh
# Run 29 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the named /tmp/fvp.txt mapping (line 9485).


# --- transcript line 9119  2026-09-22T20:29:35.760Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p21_fullpaint.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 130
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 8000 -id $id WM_NAME 2>/dev/null | grep 'FVP|')
  [ -n "$t" ] && echo "$t"
done
true
EOF


# --- transcript line 9128  2026-09-22T20:31:54.471Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aoE 'FVP\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/buzze8dgq.output | tail -1 > /tmp/fvp.txt
cat /tmp/fvp.txt | cut -c1-200; echo
python3 parse_fullpaint.py /tmp/fvp.txt 450 2>&1 | sed -n '1,20p'


# --- transcript line 9133  2026-09-22T20:32:50.045Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -c ": > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk"'
sleep 25; tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1
