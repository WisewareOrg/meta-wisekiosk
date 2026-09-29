#!/bin/sh
# Run 42 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the task-id chain: line 10847 starts the capture (task bj04eut75) after the JSC_forceRAMSize config-set at line 10842, staged to eager-gc-616s-raw.txt at line 11502.


# --- transcript line 10842  2026-09-23T03:40:30.720Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
cp /data/config/kiosk.conf /data/config/kiosk.conf.bak-run42
# eager-GC combo: small RAM budget + low heap-growth factors -> frequent small collections
cat >> /data/config/kiosk.conf <<'CONF'
JSC_forceRAMSize=33554432
JSC_smallHeapGrowthFactor=1.05
JSC_largeHeapGrowthFactor=1.05
CONF
echo "=== kiosk.conf ==="; cat /data/config/kiosk.conf
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 30
export DISPLAY=:0
echo "=== sanity at 30s: is it rendering? (BL payload, frames advancing) ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 4000 -id $id WM_NAME 2>/dev/null | grep -E 'BL\|'
done
echo "=== webproc up? ==="; ps w | grep -i WebKitWebProc | grep -v grep | head -1 || echo "no webproc line"
EOF


# --- transcript line 10847  2026-09-23T03:41:15.936Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
export DISPLAY=:0
sleep 585
echo "=== BL payload with eager-GC JSC options (588s) ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 12000 -id $id WM_NAME 2>/dev/null | grep -E 'BL\|'
done
echo "=== VmRSS (memory sanity under small heap) ==="
p=$(pidof WebKitWebProcess | cut -d' ' -f1); [ -n "$p" ] && grep VmRSS /proc/$p/status
echo "=== loadavg ==="; cat /proc/loadavg
echo "=== done ==="
EOF


# --- transcript line 11502  2026-09-23T05:18:28.432Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
S=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
T=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks
# save task-output raw captures to named files
cp "$T/bo2cli8hk.output" "$S/baseline-588s-raw.txt"   # Run 41 clean baseline
cp "$T/bj04eut75.output" "$S/eager-gc-616s-raw.txt"   # Run 42 JSC eager-GC env
# stage probes, parsers, tests, raw captures into the investigation dir (R2)
for f in p28_ablate.js parse_ablate.py parse_ablate_test.py ablate-475s-raw.txt \
         p29_split.js parse_split.py parse_split_test.py split-475s-raw.txt \
         p30_baseline.js baseline-588s-raw.txt eager-gc-616s-raw.txt fix1-600s-raw.txt \
         cap-probe.js p26_gc.js; do
  cp "$S/$f" ./ 2>&1 && echo "staged $f" || echo "MISSING $f"
done
echo "=== investigation dir now has (new this session) ==="; ls -1 p2[5-9]*.* p30*.* parse_ablate* parse_split* *-raw.txt cap-probe.js 2>/dev/null | sort | head -40
