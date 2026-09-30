#!/bin/sh
# Run 40 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. The `cat > script.js < p29_split.js` deploy (previously reported as a gap) is
# embedded at the end of line 10771 (its command also does a bundle-marker check first) -- a single
# clean pass, no retries, matching the split-475s-raw.txt the README cites.
# Excluded: the WiseKiosk frontend edit that produced instrumented bundle index-BM3R3o7e.js -- a
# different repository's source edit and build step, not an ssh heredoc/probe-deploy/readback
# against the kiosk (same treatment as Runs 37 and 39).

# --- transcript line 10771  2026-09-23T03:08:49.104Z ---
echo "=== bundle + markers ==="; b=$(curl -s http://<mirror>:8080/ | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1); echo "bundle: $b"; curl -s "http://<mirror>:8080/assets/$b" -o /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/served3.js; f=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/served3.js; for m in __mmReal matchmedia __abl; do echo "$m: $(grep -oc "$m" "$f")"; done; echo "container: $(docker ps --filter name=wisekiosk --format '{{.Status}}')"
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p29_split.js
echo "probe deployed: $(/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'wc -c < /home/root/.surf/script.js')"


# --- transcript line 10776  2026-09-23T03:08:56.949Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 475
export DISPLAY=:0
echo "=== SP final payload ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 12000 -id $id WM_NAME 2>/dev/null | grep -E 'SP\|'
done
echo "=== loadavg ==="; cat /proc/loadavg
echo "=== done ==="
EOF


# --- transcript line 10802  2026-09-23T03:17:01.555Z ---
cp /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bv7mjzv8j.output /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/split-475s-raw.txt
cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/split-475s-raw.txt
echo; echo "=== parsed ==="
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 parse_split.py split-475s-raw.txt "Run 40 — rotation-driver split (prod, BM3R3o7e, 720p)"
