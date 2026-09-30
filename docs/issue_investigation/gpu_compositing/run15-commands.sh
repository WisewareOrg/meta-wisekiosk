#!/bin/sh
# Run 15 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: subagent agent-adeb77092a2242020.jsonl
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Single deploy+capture (p9_area.js -> area-raw.txt), no retries found. The probe's own `Write` was not isolated in this pass (p9_area.js is already committed beside the README, so its content is not in question) -- only the deploy+capture command is included.

# --- adeb77092a2242020 line 1046  2026-09-22T13:07:32.618Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < "$SP/p9_area.js"
echo "install-rc=$?"
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'wc -c < /home/root/.surf/script.js'
timeout 600 /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' > "$SP/area-raw.txt" 2>&1 <<'EOF'
systemctl restart kiosk
sleep 445
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  xprop -len 8000 -id $id WM_NAME 2>/dev/null | grep 'FA|'
done
echo "LOAD $(cat /proc/loadavg)"
EOF
echo "capture-rc=$?"
