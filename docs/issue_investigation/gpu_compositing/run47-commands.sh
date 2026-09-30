#!/bin/sh
# Run 47 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Both arm scripts (arm1-baseline.sh, arm2-monitor-off.sh) are Written verbatim then invoked once each; their task outputs (bu2x8ct82, bv2ict5ht) are the same files already recovered as this run's raw captures, so the number-to-command match is exact, not inferred.
# NOTE: Full arm scripts (arm1-baseline.sh, arm2-monitor-off.sh) included verbatim as Written, then their invocation. These are the same task-output files already staged as memory-pressure-baseline-588s-raw.txt / memory-pressure-monitoroff-589s-raw.txt.

# --- transcript line 12662  2026-09-23T11:39:01.378Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p30_baseline.js
echo "deploy rc=$?"
tools/kiosk-ssh.sh root@<prod> 'wc -c /home/root/.surf/script.js; cp /data/config/kiosk.conf /data/config/kiosk.conf.mptest.bak; echo backup-rc=$?; ls -la /data/config/kiosk.conf.mptest.bak'


# --- transcript line 12673  2026-09-23T11:39:46.496Z ---
# Write -> /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/arm1-baseline.sh
cat > arm1-baseline.sh <<'PROBE_EOF'
#!/bin/sh
# Arm 1 — BASELINE (memory-pressure monitor at default ON). Adds only JSC GC logging so we get
# the first real collection trace in the current board state. Log -> /data (not tmpfs).
cp /data/config/kiosk.conf.mptest.bak /data/config/kiosk.conf
printf 'JSC_logGC=1\nWTF_DATA_LOG_FILENAME=/data/gc\n' >> /data/config/kiosk.conf
echo "=== kiosk.conf now ==="; cat /data/config/kiosk.conf
rm -f /data/gc.*.txt
rm -rf /home/root/.surf/cache
systemctl restart kiosk
echo "restarted, sleeping 600"
sleep 600
export DISPLAY=:0
echo "=== WM_NAME (BL) ==="
for id in $(xwininfo -root -children | grep '0x' | awk '{print $1}'); do
  xprop -len 8000 -id $id WM_NAME | grep 'BL|'
done
echo "=== LOAD ==="; cat /proc/loadavg
echo "=== MEM ==="; grep -E 'MemTotal|MemAvailable' /proc/meminfo
p=$(pidof WebKitWebProcess); echo "webpid=$p"; [ -n "$p" ] && grep VmRSS /proc/$p/status
echo "=== GC files ==="; ls -la /data/gc.*.txt 2>&1
for f in /data/gc.*.txt; do
  [ -e "$f" ] || continue
  echo "--- $f size/lines ---"; wc -c "$f"; wc -l "$f"
  echo "--- FullCollection count ---"; grep -a -c 'FullCollection' "$f"
  echo "--- EdenCollection count ---"; grep -a -c 'EdenCollection' "$f"
  echo "--- FullCollection lines (tail 30) ---"; grep -a 'FullCollection' "$f" | tail -30
  echo "--- raw tail 40 ---"; tail -40 "$f"
done
echo "=== ARM1 DONE ==="

PROBE_EOF


# --- transcript line 12677  2026-09-23T11:39:50.279Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/arm1-baseline.sh


# --- transcript line 12693  2026-09-23T11:40:58.797Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sleep 90; echo "=== is-active ==="; systemctl is-active kiosk; echo "=== webpid ==="; pidof WebKitWebProcess; echo "=== GC files ==="; ls -la /data/gc.*.txt 2>&1; echo "=== GC sample (head) ==="; for f in /data/gc.*.txt; do [ -e "$f" ] && { echo "-- $f --"; head -8 "$f"; wc -l "$f"; }; done'


# --- transcript line 12698  2026-09-23T11:41:30.932Z ---
# Write -> /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/arm2-monitor-off.sh
cat > arm2-monitor-off.sh <<'PROBE_EOF'
#!/bin/sh
# Arm 2 — MONITOR OFF. The complete kill switch (WEBKIT_DISABLE_MEMORY_PRESSURE_MONITOR=1 suppresses
# the whole handler via shouldSuppressMemoryPressureHandler). Same GC logging as Arm 1.
cp /data/config/kiosk.conf.mptest.bak /data/config/kiosk.conf
printf 'WEBKIT_DISABLE_MEMORY_PRESSURE_MONITOR=1\nJSC_logGC=1\nWTF_DATA_LOG_FILENAME=/data/gc\n' >> /data/config/kiosk.conf
echo "=== kiosk.conf now ==="; cat /data/config/kiosk.conf
rm -f /data/gc.*.txt
rm -rf /home/root/.surf/cache
systemctl restart kiosk
echo "restarted, sleeping 600"
sleep 600
export DISPLAY=:0
echo "=== WM_NAME (BL) ==="
for id in $(xwininfo -root -children | grep '0x' | awk '{print $1}'); do
  xprop -len 8000 -id $id WM_NAME | grep 'BL|'
done
echo "=== LOAD ==="; cat /proc/loadavg
echo "=== MEM ==="; grep -E 'MemTotal|MemAvailable' /proc/meminfo
p=$(pidof WebKitWebProcess); echo "webpid=$p"; [ -n "$p" ] && grep VmRSS /proc/$p/status
echo "=== GC files ==="; ls -la /data/gc.*.txt 2>&1
for f in /data/gc.*.txt; do
  [ -e "$f" ] || continue
  echo "--- $f size/lines ---"; wc -c "$f"; wc -l "$f"
  echo "--- FullCollection count ---"; grep -a -c 'FullCollection' "$f"
  echo "--- EdenCollection count ---"; grep -a -c 'EdenCollection' "$f"
  echo "--- FullCollection lines (tail 30) ---"; grep -a 'FullCollection' "$f" | tail -30
  echo "--- raw tail 40 ---"; tail -40 "$f"
done
echo "=== ARM2 DONE ==="

PROBE_EOF


# --- transcript line 12760  2026-09-23T11:50:48.443Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/arm2-monitor-off.sh
