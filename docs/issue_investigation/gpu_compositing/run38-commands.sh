#!/bin/sh
# Run 38 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: MEDIUM. Both CAP| and GC2| payloads were read directly out of a tool_result (lines 10538/10554), not a staged file, and are byte-identical to what the README's Run 38 block and cap-probe-raw.txt quote -- HIGH confidence on the payloads themselves. MEDIUM overall because two cap-probe.js iterations exist (lines 10521, 10527) and this pass did not diff them against the committed cap-probe.js to confirm which one is byte-identical to it.
# NOTE: Two probe iterations kept (L10521, L10527) because the committed cap-probe.js may not be byte-identical to the deployed one -- diff before assuming which is final. Excluded: L10505/L10510, general JSC_logGC/surf-milestones.log characterisation not specific to this run's CAP|/GC2| payloads.

# --- transcript line 10521  2026-09-23T02:36:57.176Z ---
cat > /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/cap-probe.js <<'JS'
// Capability probe: which in-page GC instruments does this WebKit expose?
(function () {
  function snap() {
    var m = performance.memory;
    return m ? (Math.round(m.usedJSHeapSize / 1e6 * 10) / 10) : null;
  }
  var m = performance.memory;
  var a = snap();
  // churn some garbage, then re-sample to see if usedJSHeapSize actually moves
  var junk = []; for (var i = 0; i < 200000; i++) junk.push({ x: i, s: 's' + i }); junk = null;
  var b = snap();
  var s = 'CAP|pm:' + (m
        ? ('used' + (m.usedJSHeapSize / 1e6).toFixed(1) + '/tot' + (m.totalJSHeapSize / 1e6).toFixed(1)
           + '/lim' + (m.jsHeapSizeLimit / 1e6).toFixed(0) + '/moved' + (a !== null && b !== null ? (b - a).toFixed(2) : '?'))
        : 'NONE')
    + '|FinalizationRegistry:' + (typeof FinalizationRegistry)
    + '|WeakRef:' + (typeof WeakRef)
    + '|gc:' + (typeof window.gc)
    + '|queueMicrotask:' + (typeof queueMicrotask)
    + '|' + (navigator.userAgent.match(/AppleWebKit\/[\d.]+/) || ['ua?'])[0];
  document.title = s;
})();
JS
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/cap-probe.js
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 14
export DISPLAY=:0
for id in $(xwininfo -root -children | grep '0x' | awk '{print $1}'); do
  xprop -len 2000 -id $id WM_NAME | grep -E 'CAP\|'
done
EOF


# --- transcript line 10527  2026-09-23T02:37:44.293Z ---
cat > /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/cap-probe.js <<'JS'
// Capability probe: which in-page GC instruments does this WebKit expose?
(function () {
  var m = performance.memory;
  var a = m ? m.usedJSHeapSize : null;
  var junk = []; for (var i = 0; i < 200000; i++) junk.push({ x: i, s: 's' + i }); junk = null;
  var b = m ? m.usedJSHeapSize : null;
  var s = 'CAP|pm:' + (m
        ? ('used' + (m.usedJSHeapSize / 1e6).toFixed(1) + '/tot' + (m.totalJSHeapSize / 1e6).toFixed(1)
           + '/lim' + (m.jsHeapSizeLimit / 1e6).toFixed(0) + '/moved' + ((b - a) / 1e6).toFixed(2))
        : 'NONE')
    + '|FinalizationRegistry:' + (typeof FinalizationRegistry)
    + '|WeakRef:' + (typeof WeakRef)
    + '|gc:' + (typeof window.gc)
    + '|qMt:' + (typeof queueMicrotask)
    + '|' + (navigator.userAgent.match(/AppleWebKit\/[\d.]+/) || ['ua?'])[0];
  // keep re-asserting so the app's own document.title cannot clobber it
  window.setInterval(function () { document.title = s; }, 1000);
  document.title = s;
})();
JS
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/cap-probe.js
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 16
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 2000 -id $id WM_NAME 2>/dev/null | grep -E 'CAP\|'
done
EOF


# --- transcript line 10537  2026-09-23T02:38:21.655Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
export DISPLAY=:0
echo "=== all window WM_NAMEs (raw) ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  t=$(xprop -len 3000 -id $id WM_NAME 2>/dev/null)
  case "$t" in *WM_NAME*) echo "$id: $t";; esac
done
echo "=== script.js on board (size + head) ==="
wc -c < /home/root/.surf/script.js
head -c 120 /home/root/.surf/script.js; echo
echo "=== surf log: load + any error lines ==="
grep -E 'load_finished|load_committed|Error|error|exception|Uncaught' /var/log/surf-milestones.log | tail -n 8
EOF


# --- transcript line 10542  2026-09-23T02:40:05.769Z ---
cat > /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p26_gc.js <<'JS'
// GC ground-truth probe (meta-wisekiosk #100, Run 38). Installed at ~/.surf/script.js.
//
// performance.memory is absent on this WebKit (605.1.15), but FinalizationRegistry is present.
// A finalizer fires only after a GC reclaims its token, so we detect GC events in-band:
//   - Sentinel objects are held in a ring for ~SURVIVE_S seconds -> they survive many cheap Eden
//     collections and are PROMOTED to the old generation. When the ring overwrites one it becomes
//     old-generation garbage, reclaimable only by a FULL (old-gen) collection -- the ~1s pause.
//   - Its finalizer then fires; a burst of finalizer callbacks marks a full GC, timestamped.
// The same probe times every frame and records >250ms stalls with timestamps. If the stall
// timestamps line up with the finalizer bursts, the residual stall IS a full GC (ground truth).
// Exfil GC2| through document.title, read with xprop.
(function () {
  if (window.__kp26) return; window.__kp26 = 1;
  var t0 = performance.now(), prev = t0;
  var frames = 0, big = 0, finalizeCount = 0, lastFin = -1e9;
  var stalls = [];    // [t(0.1s), dt(ms)] for frames > 250ms
  var gcEvents = [];  // t(0.1s) of each finalizer burst (>=1 old-gen sentinel reclaimed => full GC)

  var reg = new FinalizationRegistry(function () {
    var now = performance.now();
    finalizeCount++;
    if (now - lastFin > 250) { if (gcEvents.length < 240) gcEvents.push(Math.round((now - t0) / 100) / 10); }
    lastFin = now;
  });

  // One promoted sentinel per second, dropped SURVIVE_S later so only a full GC frees it.
  var SURVIVE_S = 40, ring = new Array(SURVIVE_S), seq = 0;
  window.setInterval(function () {
    var s = { seq: seq, pad: new Array(40).join('x') };
    reg.register(s, seq);
    ring[seq % SURVIVE_S] = s;   // overwrites the sentinel from SURVIVE_S s ago -> old-gen garbage
    seq++;
  }, 1000);

  var RAF = window.requestAnimationFrame.bind(window);
  function tick(now) {
    var dt = now - prev; prev = now; frames++;
    if (dt > 250) { big++; if (stalls.length < 240) stalls.push([Math.round((now - t0) / 100) / 10, Math.round(dt)]); }
    RAF(tick);
  }
  RAF(tick);

  window.setInterval(function () {
    var el = Math.round((performance.now() - t0) / 1000);
    var st = stalls.map(function (e) { return e[0] + ':' + e[1]; }).join(',');
    document.title = 'GC2|' + el + '|f' + frames + '|big' + big + '|fin' + finalizeCount +
      '|S[' + st + ']|G[' + gcEvents.join(',') + ']';
  }, 2000);
})();
JS
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p26_gc.js
echo "deployed $(wc -c < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p26_gc.js) bytes"
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 185
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 8000 -id $id WM_NAME 2>/dev/null | grep -E 'GC2\|'
done
EOF


# --- transcript line 10553  2026-09-23T02:42:16.796Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 8000 -id $id WM_NAME 2>/dev/null | grep -E 'GC2\|'
done
EOF
