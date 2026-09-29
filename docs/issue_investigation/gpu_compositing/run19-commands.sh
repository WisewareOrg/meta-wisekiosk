#!/bin/sh
# Run 19 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Config switched to compositing ON (drops WEBKIT_DISABLE_DMABUF_RENDERER), verified via the webprocess environ and gpu-check, then `run-phase-motion.sh p12_motion.js 450` -> motion-compositing-on-raw.txt. Single pass, no retries.

# --- main line 7648  2026-09-22T15:05:55.089Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
# clean page (drop leftover steps probe)
: > /home/root/.surf/script.js
# compositing ON: drop the DISABLE_DMABUF_RENDERER line, keep vblank timer
cat > /data/config/kiosk.conf.new <<'CONF'
KIOSK_URL=http://<mirror>:8080/
KIOSK_INSPECTOR=0
WEBKIT_FORCE_VBLANK_TIMER=1
CONF
sync; mv /data/config/kiosk.conf.new /data/config/kiosk.conf; sync
echo "-- new live config --"; cat /data/config/kiosk.conf
rm -rf /home/root/.surf/cache
systemctl restart kiosk
echo "restarted; waiting for load"
sleep 30
echo "-- webprocess environ check (DMABUF should be ABSENT) --"
p=$(pidof WebKitWebProcess | tr ' ' '\n' | head -1)
echo "webproc pid=$p"
[ -n "$p" ] && tr '\0' '\n' < /proc/$p/environ | grep -E 'DMABUF|VBLANK|COMPOSIT' || echo "(no matching env)"
EOF

# --- main line 7653  2026-09-22T15:06:52.404Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "-- kiosk service --"; systemctl is-active kiosk; systemctl show kiosk -p NRestarts --value 2>/dev/null | sed 's/^/NRestarts=/'
echo "-- processes --"; pidof WebKitWebProcess; pidof surf; pidof Xorg
p=$(pidof WebKitWebProcess); p=${p%% *}
echo "webproc pid=$p"
if [ -n "$p" ]; then
  echo "-- env (dmabuf/vblank) --"; tr '\0' '\n' < /proc/$p/environ | grep -E 'DMABUF|VBLANK'
  echo "-- /dev/dri open + gallium driver (compositing proxy) --"
  ls -l /proc/$p/fd 2>/dev/null | grep -o '/dev/dri/[a-zA-Z0-9]*' | sort -u
  tr '\0' '\n' < /proc/$p/maps 2>/dev/null | grep -oE '(vc4|v3d)_dri\.so|swrast_dri\.so' | sort -u
fi
EOF

# --- main line 7664  2026-09-22T15:07:09.150Z ---
cd /home/tjwise/meta-wisekiosk
mkdir -p /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/shots
echo "==== gpu-check verdict ===="
tools/kiosk-gpu-check.sh root@<prod> 2>&1 | tail -15
echo "==== screenshot ===="
tools/kiosk-screenshot.sh root@<prod> /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/shots/compositing-on.png 2>&1 | tail -8
ls -la /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/shots/ 2>/dev/null

# --- main line 7687  2026-09-22T15:08:17.295Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
./run-phase-motion.sh root@<prod> p12_motion.js 450 > motion-compositing-on-raw.txt 2>&1
echo "EXIT=$?"; grep -aoE 'KP2\|[^"]*' motion-compositing-on-raw.txt | tail -1 | cut -c1-160

# --- main line 7745  2026-09-22T15:16:36.428Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
python3 parse_motion.py motion-compositing-on-raw.txt "COMPOSITING-ON (dmabuf renderer, vc4/mesa), prod 7ce44ba" 2>&1 | sed -n '1,4p;/DURING-MOTION/,/7 rows/p'
