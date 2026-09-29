#!/bin/sh
# Run 45 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. The config-set command (previously reported as a gap) is at line 11766: it sets
# `JSC_percentCPUPerMBForFullTimer=1.953125e-05` (the default divided by 16, matching the README's
# "16x less eager full-collection timer") and deploys p30_baseline.js in the same command, immediately
# followed by the restart+poll+readback at line 11771. Single clean pass, no retries found.

# --- transcript line 11766  2026-09-23T05:52:52.563Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p30_baseline.js
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
cp /data/config/kiosk.conf.bak-run38 /data/config/kiosk.conf
cat >> /data/config/kiosk.conf <<'CONF'
JSC_logGC=1
JSC_percentCPUPerMBForFullTimer=1.953125e-05
CONF
echo "=== kiosk.conf ==="; cat /data/config/kiosk.conf
: > /var/log/surf-milestones.log
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 20
echo "=== early logGC lines (does it print per-collection with p=?) ==="
grep -aE '\[GC|FullCollection|EdenCollection|p=' /var/log/surf-milestones.log | tail -6 || echo "(none yet)"
EOF

# --- transcript line 11771  2026-09-23T05:53:39.308Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
export DISPLAY=:0
sleep 500
echo "=== in-page stall payload (frequency lever P/16, 500s) ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 12000 -id $id WM_NAME 2>/dev/null | grep -E 'BL\|'
done
echo "=== GC log: count + the large (full-GC) pauses ==="
grep -acE '\[GC' /var/log/surf-milestones.log
echo "--- GC lines with pause >= 100ms (full collections) ---"
grep -aoE 'starting [0-9.]+ms' /var/log/surf-milestones.log | awk '{if ($2+0 >= 100) print}' | sort -t' ' -k2 -n | tail -20
echo "--- total GC lines, and max pause ---"
grep -aoE 'starting [0-9.]+ms' /var/log/surf-milestones.log | awk '{print $2+0}' | sort -n | tail -3
echo "=== done ==="
EOF


# --- transcript line 12054  2026-09-23T06:28:45.566Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
T=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks
cp "$T/bvzgwcubo.output" ./freq-lever-P16-535s-raw.txt
cp "$T/bkgw1q1o7.output" ./imperative-tour-587s-raw.txt
echo "staged freq-lever + imperative-tour raw captures"
ls -1 freq-lever-P16-535s-raw.txt imperative-tour-587s-raw.txt fix1-benchmark-600s-raw.txt
