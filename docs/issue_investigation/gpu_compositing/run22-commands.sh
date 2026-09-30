#!/bin/sh
# Run 22 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# kiosk-launch patched to force 1280x720 via xrandr, verified, then run-phase-motion.sh (p12_motion.js -> motion-720p-raw.txt). Single pass, no retries.

# --- main line 7935  2026-09-22T16:10:50.276Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
cp /usr/bin/kiosk-launch /usr/bin/kiosk-launch.bak-1080p && echo "backed up"
sed -i 's#^exec surf#xrandr --output HDMI-1 --mode 1280x720 2>/dev/null\nexec surf#' /usr/bin/kiosk-launch
echo "-- result (last 4 lines) --"
tail -4 /usr/bin/kiosk-launch
echo "-- xrandr line present? --"
grep -c 'mode 1280x720' /usr/bin/kiosk-launch
EOF

# --- main line 7940  2026-09-22T16:11:00.124Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
: > /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 28
export DISPLAY=:0
echo "-- current mode --"; xrandr 2>/dev/null | grep -E '\*|Screen 0'
echo "-- surf window size --"
for id in $(xwininfo -root -children 2>/dev/null | grep -i surf | awk '{print $1}'); do xwininfo -id $id 2>/dev/null | grep -E 'Width|Height'; done
echo "-- kiosk active --"; systemctl is-active kiosk
EOF

# --- main line 7959  2026-09-22T16:12:07.219Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p12_motion.js 450 > motion-720p-raw.txt 2>&1
echo "EXIT=$?"; grep -aoE 'KP2\|[^"]*' motion-720p-raw.txt | tail -1 | cut -c1-150

# --- main line 7968  2026-09-22T16:19:44.304Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 parse_motion.py motion-720p-raw.txt "720p during-motion, prod 7ce44ba" 2>&1 | sed -n '1,4p;/DURING-MOTION/,/7 rows/p'
