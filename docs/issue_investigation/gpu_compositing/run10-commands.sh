#!/bin/sh
# Run 10 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: subagent agent-adeb77092a2242020.jsonl
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Single deploy+capture (p5_clock.js -> clock-ablation-raw.txt), no retries found; several identical polling one-liners waiting for the background ssh to finish were collapsed out (see MANIFEST).

# --- adeb77092a2242020 line 199  2026-09-22T12:14:21.587Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < "$SP/p5_clock.js"
echo "write-rc=$?"
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'wc -c < /home/root/.surf/script.js'
wc -c < "$SP/p5_clock.js"

# --- adeb77092a2242020 line 201  2026-09-22T12:14:30.599Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
timeout 560 /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' > "$SP/clock-ablation-raw.txt" 2>&1 <<'EOF'
systemctl restart kiosk
sleep 400
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  xprop -len 8000 -id $id WM_NAME 2>/dev/null | grep 'KP|'
done
echo "LOAD $(cat /proc/loadavg)"
p=$(pidof WebKitWebProcess | cut -d' ' -f1)
[ -n "$p" ] && grep VmRSS /proc/$p/status
EOF
rc=$?
echo "capture-rc=$rc"
wc -c < "$SP/clock-ablation-raw.txt"

# --- adeb77092a2242020 line 207  2026-09-22T12:16:54.452Z ---
until [ -s /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/clock-ablation-raw.txt ] && grep -q 'LOAD ' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/clock-ablation-raw.txt; do sleep 20; done; echo "capture complete"

# --- adeb77092a2242020 line 211  2026-09-22T12:17:03.681Z ---
sleep 240; cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/clock-ablation-raw.txt 2>/dev/null | head -c 400; echo; echo "---"; ls -la /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/clock-ablation-raw.txt

# --- adeb77092a2242020 line 216  2026-09-22T12:17:11.574Z ---
sleep 200; f=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/clock-ablation-raw.txt; wc -c < "$f"; grep -c 'KA|' "$f"

# --- adeb77092a2242020 line 224  2026-09-22T12:17:31.553Z ---
f=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/clock-ablation-raw.txt
until grep -q 'LOAD ' "$f" 2>/dev/null; do sleep 15; done
echo "CAPTURE COMPLETE"
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 parse_arms.py clock-ablation-raw.txt

# --- adeb77092a2242020 line 257  2026-09-22T12:18:56.747Z ---
f=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/clock-ablation-raw.txt
ps -eo pid,etime,args | grep -c '[s]sh .*<prod>'
wc -c < "$f"

# --- adeb77092a2242020 line 265  2026-09-22T12:19:44.267Z ---
f=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/clock-ablation-raw.txt
ps -eo etime,args | grep '[s]sh .*<prod>' | head -2
echo "bytes=$(wc -c < "$f")"
cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bi0tjm6z6.output

# --- adeb77092a2242020 line 269  2026-09-22T12:19:53.249Z ---
f=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/clock-ablation-raw.txt
until grep -q 'LOAD ' "$f" 2>/dev/null; do sleep 10; done
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
echo "=== raw bytes: $(wc -c < "$f")"
python3 parse_arms.py clock-ablation-raw.txt
echo "=== tail of raw ==="
grep -E 'LOAD|VmRSS' clock-ablation-raw.txt
