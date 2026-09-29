#!/bin/sh
# Run 28 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the named /tmp/pf.txt mapping (line 9485).


# --- transcript line 8891  2026-09-22T19:51:51.999Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p20_profile.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 300
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 30000 -id $id WM_NAME 2>/dev/null | grep 'PF|')
  [ -n "$t" ] && echo "$t"
done
true
EOF


# --- transcript line 8906  2026-09-22T19:57:01.530Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aoE 'PF\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b0hbd41yq.output | tail -1 > /tmp/pf.txt
cat /tmp/pf.txt | cut -c1-200
echo "=== parse ==="
python3 parse_profile.py /tmp/pf.txt "layout-vs-paint attribution" 2>&1 | sed -n '1,30p'
