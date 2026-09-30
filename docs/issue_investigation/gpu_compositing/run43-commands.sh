#!/bin/sh
# Run 43 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the task-id chain: line 11497 starts the capture (task by4x5pedr) after the clean-config restore at line 11492, staged to fix1-benchmark-600s-raw.txt at line 11563.


# --- transcript line 11492  2026-09-23T05:16:49.024Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p30_baseline.js
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
cp /data/config/kiosk.conf.bak-run38 /data/config/kiosk.conf
echo "=== clean kiosk.conf ==="; cat /data/config/kiosk.conf
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 20
export DISPLAY=:0
echo "=== sanity (rendering, no inspector perturbation) ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 2000 -id $id WM_NAME 2>/dev/null | grep -E 'BL\|'
done
EOF


# --- transcript line 11497  2026-09-23T05:17:21.996Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
export DISPLAY=:0
sleep 590
echo "=== FINAL BENCHMARK: safe-fix state (marquee+clock split+matchMedia cache), bundle BhI9T8Rb, clean config ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 12000 -id $id WM_NAME 2>/dev/null | grep -E 'BL\|'
done
echo "=== loadavg ==="; cat /proc/loadavg
echo "=== done ==="
EOF


# --- transcript line 11563  2026-09-23T05:27:58.183Z ---
echo "=== Fix-1 benchmark result ==="; grep -oE 'BL\|[0-9]+\|f[0-9]+\|big[0-9]+\|av[0-9]+\|mx[0-9]+' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/by4x5pedr.output | head -1; echo "--- stall timestamps ---"; grep -oE 'S\[[^]]*\]' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/by4x5pedr.output | head -1; cp /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/by4x5pedr.output /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing/fix1-benchmark-600s-raw.txt
