#!/bin/sh
# Run 8 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: subagent agent-abead48aed7895c20.jsonl
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Single clean pass, no retries: probe4.tmpl.js/run-phase.sh/parse4.py written, then `./run-phase.sh p4_a.js 330 > phaseA.txt`, `p4_b.js 300 > phaseB.txt`, `p4_d.js 300 > phaseD.txt`, `p4_a.js 300 > phaseA2.txt` -- matching exactly the four raw files the README's Run 8 catalogue names (phaseA.txt/phaseA2.txt/phaseB.txt/phaseD.txt), each read immediately after by parse4.py with a label matching the README's own per-arm description.

# --- abead48aed7895c20 line 146  2026-09-22T04:04:03.038Z  (Write) ---
cat > probe4.tmpl.js <<'PROBE_EOF'
(function () {
  if (window.__kp) return;
  window.__kp = 1;

  var t0 = performance.now();
  var layoutMs = 0, layoutN = 0, jsMs = 0;

  function wrapGetter(proto, prop) {
    var d = Object.getOwnPropertyDescriptor(proto, prop);
    if (!d || !d.get) return;
    var orig = d.get;
    Object.defineProperty(proto, prop, {
      configurable: true,
      enumerable: d.enumerable,
      get: function () {
        var a = performance.now();
        var v = orig.call(this);
        layoutMs += performance.now() - a;
        layoutN++;
        return v;
      }
    });
  }

  function wrapMethod(obj, name) {
    var orig = obj[name];
    if (typeof orig !== 'function') return;
    obj[name] = function () {
      var a = performance.now();
      var v = orig.apply(this, arguments);
      layoutMs += performance.now() - a;
      layoutN++;
      return v;
    };
  }

  ['scrollWidth', 'scrollHeight', 'clientWidth', 'clientHeight'].forEach(function (p) {
    wrapGetter(Element.prototype, p);
  });
  ['offsetWidth', 'offsetHeight', 'offsetTop', 'offsetLeft'].forEach(function (p) {
    wrapGetter(HTMLElement.prototype, p);
  });
  wrapMethod(Element.prototype, 'getBoundingClientRect');
  wrapMethod(window, 'getComputedStyle');

  function timed(fn) {
    return function () {
      var a = performance.now();
      try { return fn.apply(this, arguments); }
      finally { jsMs += performance.now() - a; }
    };
  }

  var origRaf = window.requestAnimationFrame.bind(window);
  var origSetTimeout = window.setTimeout.bind(window);
  var origSetInterval = window.setInterval.bind(window);

  window.requestAnimationFrame = function (cb) {
    return origRaf(typeof cb === 'function' ? timed(cb) : cb);
  };
  window.setTimeout = function (cb) {
    var rest = Array.prototype.slice.call(arguments, 1);
    return origSetTimeout.apply(null, [typeof cb === 'function' ? timed(cb) : cb].concat(rest));
  };
  window.setInterval = function (cb) {
    var rest = Array.prototype.slice.call(arguments, 1);
    return origSetInterval.apply(null, [typeof cb === 'function' ? timed(cb) : cb].concat(rest));
  };
  var origQmt = window.queueMicrotask ? window.queueMicrotask.bind(window) : null;
  if (origQmt) {
    window.queueMicrotask = function (cb) {
      return origQmt(typeof cb === 'function' ? timed(cb) : cb);
    };
  }

/*ABLATION*/

  var rotN = 0, lastRotT = -1e9, pendingRot = 0, firstRotT = 0;

  var mo = new MutationObserver(function (recs) {
    var n = 0;
    for (var i = 0; i < recs.length; i++) {
      var r = recs[i];
      if (r.addedNodes.length === 0 && r.removedNodes.length === 0) continue;
      var tgt = r.target;
      if (tgt && tgt.closest && tgt.closest('[data-pwt-ride-name]')) {
        n += r.addedNodes.length + r.removedNodes.length;
      }
    }
    if (n === 0) return;
    var t = performance.now() - t0;
    pendingRot += n;
    if (t - lastRotT > 1500) {
      if (rotN === 0) firstRotT = t;
      rotN++;
      lastRotT = t;
    }
  });

  function observe() {
    if (document.body) {
      mo.observe(document.body, { childList: true, subtree: true });
    } else {
      origSetTimeout(observe, 200);
    }
  }
  observe();

  var EDGES = [50, 100, 250, 500, 1000, 2000];
  var hist = [0, 0, 0, 0, 0, 0, 0];

  // Frame cost binned by seconds elapsed since the last rotation remount.
  var PH = 9;
  var phMs = [], phN = [], phBig = [];
  for (var i = 0; i < PH; i++) { phMs.push(0); phN.push(0); phBig.push(0); }

  // Frame cost binned by absolute 10 s window, to expose drift and the 5 min poll.
  var WIN = 10000, wMs = [], wN = [];

  var big = [], bigTotal = 0, frames = 0, sumFrame = 0, maxFrame = 0, top = [];
  var prev = performance.now();
  var THRESH = 250;

  function tick(now) {
    var dt = now - prev;
    prev = now;
    var el = now - t0;
    frames++;
    sumFrame += dt;
    if (dt > maxFrame) maxFrame = dt;

    var b = 0;
    while (b < EDGES.length && dt >= EDGES[b]) b++;
    hist[b]++;

    var ph = Math.floor((el - lastRotT) / 1000);
    if (ph < 0) ph = PH - 1;
    if (ph >= PH) ph = PH - 1;
    phMs[ph] += dt; phN[ph]++;

    var w = Math.floor(el / WIN);
    while (wMs.length <= w) { wMs.push(0); wN.push(0); }
    wMs[w] += dt; wN[w]++;

    if (dt > THRESH) {
      bigTotal++;
      phBig[ph]++;
      var rec =
        Math.round(el / 100) / 10 + ':' +
        Math.round(dt) + ':' +
        Math.round(jsMs) + ':' +
        Math.round(layoutMs) + ':' +
        layoutN + ':' +
        Math.round((el - lastRotT) / 100) / 10;
      big.push(rec);
      if (big.length > 14) big.shift();
      top.push([dt, rec]);
      top.sort(function (x, y) { return y[0] - x[0]; });
      if (top.length > 8) top.length = 8;
    }
    layoutMs = 0; layoutN = 0; jsMs = 0; pendingRot = 0;
    origRaf(tick);
  }
  origRaf(tick);

  function meanList(ms, n) {
    var o = [];
    for (var i = 0; i < ms.length; i++) o.push(n[i] ? Math.round(ms[i] / n[i]) : 0);
    return o.join('.');
  }

  origSetInterval(function () {
    var rows = document.querySelectorAll('[data-pwt-ride-name]').length;
    var mq = document.querySelectorAll('.ride-name-text.marquee').length;
    var el = performance.now() - t0;
    document.title =
      'KP|' + Math.round(el / 1000) +
      '|f' + frames +
      '|mx' + Math.round(maxFrame) +
      '|av' + Math.round(sumFrame / Math.max(frames, 1)) +
      '|M' + mq + '/' + rows +
      '|ROT' + rotN + '@' + Math.round((el - firstRotT) / Math.max(rotN - 1, 1)) +
      '|H' + hist.join('.') +
      '|PM' + meanList(phMs, phN) +
      '|PN' + phN.join('.') +
      '|PB' + phBig.join('.') +
      '|W' + meanList(wMs, wN) +
      '|BT' + bigTotal +
      '|T' + top.map(function (e) { return e[1]; }).join(',') +
      '|B' + big.join(',');
  }, 2000);
})();

PROBE_EOF

# --- abead48aed7895c20 line 151  2026-09-22T04:04:23.940Z  (Write) ---
cat > run-phase.sh <<'PROBE_EOF'
#!/usr/bin/env bash
# Deploy one probe variant to the prod kiosk, restart onto a cleared cache, let it
# run, then read the frame-time payload back out of the X window title.
#
#   run-phase.sh <probe.js> <seconds>
#
# Recoverable over the wire: the only device state touched is ~/.surf/script.js and
# the WebKit cache, both restored by deploying a zero-byte script.js and restarting.
set -uo pipefail

PROBE=${1:?usage: run-phase.sh <probe.js> <seconds>}
SECS=${2:?usage: run-phase.sh <probe.js> <seconds>}
REPO=/home/tjwise/meta-wisekiosk
HOST=root@<prod>

"$REPO/tools/kiosk-ssh.sh" "$HOST" 'cat > /home/root/.surf/script.js' < "$PROBE" || exit 1

"$REPO/tools/kiosk-ssh.sh" "$HOST" "sh -s" <<EOF
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep $SECS
export DISPLAY=:0
for id in \$(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print \$1}'); do
  xprop -len 8000 -id \$id WM_NAME 2>/dev/null | grep 'KP|'
done
echo "LOAD \$(cat /proc/loadavg)"
p=\$(pidof WebKitWebProcess | cut -d' ' -f1)
[ -n "\$p" ] && grep VmRSS /proc/\$p/status
EOF

PROBE_EOF

# --- abead48aed7895c20 line 153  2026-09-22T04:04:28.404Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && chmod +x run-phase.sh && ./run-phase.sh p4_a.js 330 > phaseA.txt 2>&1; echo "rc=$?"; cat phaseA.txt

# --- abead48aed7895c20 line 163  2026-09-22T04:10:09.243Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 parse4.py phaseA.txt "PHASE A - as deployed (7 scrolling rows)"; echo; grep -E 'LOAD|VmRSS' phaseA.txt

# --- abead48aed7895c20 line 171  2026-09-22T04:11:01.680Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && ./run-phase.sh p4_b.js 300 > phaseB.txt 2>&1; echo "rc=$?"

# --- abead48aed7895c20 line 185  2026-09-22T04:16:09.257Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 parse4.py phaseB.txt "PHASE B - animation:none + will-change:auto"; echo; grep -E 'LOAD|VmRSS' phaseB.txt

# --- abead48aed7895c20 line 189  2026-09-22T04:17:51.974Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && ./run-phase.sh p4_d.js 300 > phaseD.txt 2>&1; echo "rc=$?"; ./run-phase.sh p4_a.js 300 > phaseA2.txt 2>&1; echo "rc2=$?"

# --- abead48aed7895c20 line 208  2026-09-22T04:28:03.116Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 parse4.py phaseD.txt "PHASE D - scrolling rows capped at 2" 2>&1 | head -n 32; echo; echo "########"; python3 parse4.py phaseA2.txt "PHASE A2 - baseline repeat" 2>&1 | head -n 32
