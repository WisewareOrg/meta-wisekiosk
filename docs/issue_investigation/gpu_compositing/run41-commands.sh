#!/bin/sh
# Run 41 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the task-id chain: line 10823 starts the capture (task bo2cli8hk), staged to baseline-588s-raw.txt at line 11502 -- the README's own "reference" run.


# --- transcript line 10820  2026-09-23T03:29:15.246Z ---
cat > /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p30_baseline.js <<'JS'
// Plain long baseline (meta-wisekiosk #100, Run 41). No ablation — window.__abl left unset, so the
// app runs normally. Records >250ms stall timestamps to characterize the bursty arrival and give a
// same-session reference for the JSC GC-tuning test. Exfil BL| via document.title, read with xprop.
(function () {
  if (window.__kp30) return; window.__kp30 = 1;
  var RAF = window.requestAnimationFrame.bind(window);
  var prev = performance.now(), t0 = prev;
  var frames = 0, big = 0, sum = 0, mx = 0;
  var stalls = [];
  var BUCK = [50, 100, 250, 500, 1000, 2000], hist = [0, 0, 0, 0, 0, 0, 0];
  function tick(now) {
    var dt = now - prev; prev = now; frames++; sum += dt; if (dt > mx) mx = dt;
    var b = 0; while (b < BUCK.length && dt >= BUCK[b]) b++; hist[b]++;
    if (dt > 250) { big++; if (stalls.length < 120) stalls.push([Math.round((now - t0) / 100) / 10, Math.round(dt)]); }
    RAF(tick);
  }
  RAF(tick);
  window.setInterval(function () {
    var el = Math.round((performance.now() - t0) / 1000);
    document.title = 'BL|' + el + '|f' + frames + '|big' + big + '|av' + (frames ? Math.round(sum / frames) : 0) +
      '|mx' + Math.round(mx) + '|H' + hist.join('.') +
      '|S[' + stalls.map(function (e) { return e[0] + ':' + e[1]; }).join(',') + ']';
  }, 2000);
})();
JS
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p30_baseline.js
echo "p30 deployed: $(/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'wc -c < /home/root/.surf/script.js') bytes"


# --- transcript line 10823  2026-09-23T03:29:22.178Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 600
export DISPLAY=:0
echo "=== BL baseline payload ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 12000 -id $id WM_NAME 2>/dev/null | grep -E 'BL\|'
done
echo "=== loadavg ==="; cat /proc/loadavg
echo "=== done ==="
EOF


# --- transcript line 10831  2026-09-23T03:39:28.350Z ---
cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bo2cli8hk.output


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
