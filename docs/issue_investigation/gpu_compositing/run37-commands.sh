#!/bin/sh
# Run 37 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Single deploy+restart+poll (lines 10278/10290/10295), no retries found; its MQ| payload is what mq-toggle-496s-raw.txt carries.
# NOTE: Excluded: the WiseKiosk frontend edit + `docker compose up -d --build` that produced the instrumented bundle index-CDzciXkW.js (main transcript L10195-L10242) -- a different repository's build step, not an ssh heredoc/probe-deploy/readback against the kiosk. ESCALATED: whether that edit+rebuild should also be recovered here is for the plan owner.

# --- transcript line 10278  2026-09-23T02:09:52.310Z ---
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p25_mqtoggle.js && echo "probe deployed, $(wc -c < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p25_mqtoggle.js) bytes local" && tools/kiosk-ssh.sh root@<prod> 'echo "on-board script.js: $(wc -c < /home/root/.surf/script.js) bytes"'


# --- transcript line 10290  2026-09-23T02:10:03.917Z ---
tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 45
export DISPLAY=:0
echo "=== MQ payload at ~45s ==="
for id in $(xwininfo -root -children | grep '0x' | awk '{print $1}'); do
  xprop -len 32000 -id $id WM_NAME | grep -E 'MQ\|'
done
echo "=== loadavg ==="
cat /proc/loadavg
echo "=== marquee nodes on the page cannot be read here (DOM); N is in the payload ==="
EOF


# --- transcript line 10295  2026-09-23T02:11:51.334Z ---
tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
sleep 400
export DISPLAY=:0
echo "=== MQ final payload ==="
for id in $(xwininfo -root -children | grep '0x' | awk '{print $1}'); do
  xprop -len 32000 -id $id WM_NAME | grep -E 'MQ\|'
done
echo "=== loadavg ==="; cat /proc/loadavg
p=$(pidof WebKitWebProcess | cut -d' ' -f1); [ -n "$p" ] && grep VmRSS /proc/$p/status
echo "=== done ==="
EOF
