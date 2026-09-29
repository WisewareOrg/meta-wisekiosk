#!/bin/sh
# Run 12 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: subagent agent-adeb77092a2242020.jsonl
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Two arms, each a single clean pass: no-probe baseline (xcpu.sh pushed, captured to xcpu-noprobe.log) then the p4_a.js-instrumented arm (xcpu-probe.log). Dozens of identical `echo lines=$(wc -l ...)` polling calls between deploy and analysis were collapsed out (see MANIFEST).

# --- adeb77092a2242020 line 506  2026-09-22T12:37:10.188Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /tmp/xcpu.sh' < "$SP/xcpu-sample.sh"
echo "push-rc=$?"
timeout 400 /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' > "$SP/xcpu-noprobe.log" 2>&1 <<'EOF'
: > /home/root/.surf/script.js
systemctl restart kiosk
sleep 60
sh /tmp/xcpu.sh 120
EOF
echo "b1-rc=$?"
wc -l < "$SP/xcpu-noprobe.log"

# --- adeb77092a2242020 line 531  2026-09-22T12:38:27.785Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
until [ "$(wc -l < "$SP/xcpu-noprobe.log")" -gt 1100 ]; do sleep 10; done
cd "$SP" && python3 analyze_xcpu.py xcpu-noprobe.log

# --- adeb77092a2242020 line 558  2026-09-22T12:39:17.878Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
python3 analyze_xcpu.py xcpu-noprobe.log 2>&1 | head -n 24

# --- adeb77092a2242020 line 592  2026-09-22T12:40:29.283Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < "$SP/p4_a.js"
echo "install-rc=$?"
timeout 400 /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' > "$SP/xcpu-probe.log" 2>&1 <<'EOF'
systemctl restart kiosk
sleep 60
sh /tmp/xcpu.sh 120
EOF
echo "b2-rc=$?"
wc -l < "$SP/xcpu-probe.log"

# --- adeb77092a2242020 line 634  2026-09-22T12:42:05.427Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
python3 analyze_xcpu.py xcpu-probe.log 2>&1 | head -n 12
