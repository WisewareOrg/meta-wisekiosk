#!/bin/sh
# Run 39 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the task-id chain: line 10686 starts the capture, its output (task bugrf72p1) is staged to ablate-475s-raw.txt at line 10706, matching the README's Run 39 citation exactly.
# NOTE: Excluded: the WiseKiosk frontend edit that produced instrumented bundle index-CqqUlNUO.js (main transcript, prior to L10659's rebuild) -- see Run 37's note, same escalation applies.

# --- transcript line 10676  2026-09-23T02:54:55.910Z ---
echo "=== new served bundle ==="; b=$(curl -s http://<mirror>:8080/ | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1); echo "bundle: $b"; curl -s "http://<mirror>:8080/assets/$b" -o /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/served2.js; f=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/served2.js; echo "bytes: $(wc -c <$f)"; for m in __abl __ablRotSkip __ablClkSkip; do echo "$m: $(grep -oc "$m" "$f")"; done; echo "container: $(docker ps --filter name=wisekiosk --format '{{.Status}}')"


# --- transcript line 10681  2026-09-23T02:55:12.200Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p28_ablate.js
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
# restore the clean production kiosk.conf (drops JSC_logGC + puts KIOSK_INSPECTOR back to 0)
cp /data/config/kiosk.conf.bak-run38 /data/config/kiosk.conf
echo "=== kiosk.conf (clean) ==="; cat /data/config/kiosk.conf
echo "=== probe on board ==="; wc -c < /home/root/.surf/script.js
EOF


# --- transcript line 10686  2026-09-23T02:55:25.213Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 475
export DISPLAY=:0
echo "=== AB final payload ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 12000 -id $id WM_NAME 2>/dev/null | grep -E 'AB\|'
done
echo "=== loadavg ==="; cat /proc/loadavg
echo "=== done ==="
EOF


# --- transcript line 10706  2026-09-23T03:03:32.642Z ---
cp /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bugrf72p1.output /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/ablate-475s-raw.txt
echo "=== raw ==="; cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/ablate-475s-raw.txt
echo; echo "=== parsed ==="
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 parse_ablate.py ablate-475s-raw.txt "Run 39 — subsystem ablation (prod, CqqUlNUO, 720p)"
