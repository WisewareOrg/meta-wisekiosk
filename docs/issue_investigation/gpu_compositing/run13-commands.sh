#!/bin/sh
# Run 13 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: subagent agent-adeb77092a2242020.jsonl
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Single deploy+capture (p7_min.js -> minprobe-raw.txt), no retries found.

# --- adeb77092a2242020 line 638  2026-09-22T12:42:36.905Z  (Write) ---
cat > p7_min.js <<'PROBE_EOF'
(function () {
  if (window.__kp) return;
  window.__kp = 1;

  // MINIMAL probe: a bare requestAnimationFrame frame-time loop and nothing else.
  //
  // p4_a.js -- every prior capture -- wraps scrollWidth/clientWidth/offsetWidth/
  // getBoundingClientRect/getComputedStyle with performance.now() pairs, wraps rAF,
  // setTimeout, setInterval and queueMicrotask, and runs a subtree MutationObserver plus
  // two querySelectorAll sweeps per title write. All of that lands inside
  // WebKitWebProcess, so Test B (which measured X) cannot exclude it.
  //
  // This variant removes ALL of it. If the ~1/s frames>250ms floor survives here, the
  // floor is not the instrumentation. If it collapses, it was.
  var t0 = performance.now();
  var prev = t0;
  var frames = 0, sum = 0, mx = 0, bigTotal = 0;
  var EDGES = [50, 100, 250, 500, 1000, 2000];
  var hist = [0, 0, 0, 0, 0, 0, 0];
  var big = [];

  var rAF = window.requestAnimationFrame.bind(window);

  function tick(now) {
    var dt = now - prev;
    prev = now;
    frames++;
    sum += dt;
    if (dt > mx) mx = dt;

    var b = 0;
    while (b < EDGES.length && dt >= EDGES[b]) b++;
    hist[b]++;

    if (dt > 250) {
      bigTotal++;
      big.push(Math.round((now - t0) / 100) / 10 + ':' + Math.round(dt));
      if (big.length > 14) big.shift();
    }
    rAF(tick);
  }
  rAF(tick);

  setInterval(function () {
    var el = performance.now() - t0;
    document.title =
      'MP|' + Math.round(el / 1000) +
      '|f' + frames +
      '|av' + Math.round(sum / Math.max(frames, 1)) +
      '|mx' + Math.round(mx) +
      '|BT' + bigTotal +
      '|H' + hist.join('.') +
      '|B' + big.join(',');
  }, 2000);
})();

PROBE_EOF

# --- adeb77092a2242020 line 674  2026-09-22T12:43:53.462Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < "$SP/p7_min.js"
echo "install-rc=$?"
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'wc -c < /home/root/.surf/script.js'
timeout 420 /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' > "$SP/minprobe-raw.txt" 2>&1 <<'EOF'
systemctl restart kiosk
sleep 320
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  xprop -len 8000 -id $id WM_NAME 2>/dev/null | grep 'MP|'
done
echo "LOAD $(cat /proc/loadavg)"
EOF
echo "c-rc=$?"
