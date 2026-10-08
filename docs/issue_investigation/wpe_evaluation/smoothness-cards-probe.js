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
(function () {
  if (window.__cp) return;
  window.__cp = 1;

  // Cards-live probe: a card is [data-pwt-card]; it holds live data when it also contains
  // [data-pwt-leaderboard]. A closed card carries [data-pwt-closed], a per-park API failure
  // [data-pwt-unavailable] -- neither of those is checked here, only whether the leaderboard
  // actually rendered. Logs via console.log (not document.title, so this runs alongside a
  // title-based probe without clobbering it), read from the kiosk journal under
  // --enable-write-console-messages-to-stdout=true (bundled with KIOSK_PROBE=1).
  // Payload: parse_cards_probe.py's header. c = card count, l = leaderboard count; the gate is
  // c=4 l=4.
  function sample() {
    var c = document.querySelectorAll('[data-pwt-card]').length;
    var l = document.querySelectorAll('[data-pwt-card] [data-pwt-leaderboard]').length;
    console.log('CP|t=' + Math.round(performance.now() / 1000) + '|c=' + c + '|l=' + l);
  }

  if (document.readyState === 'complete') {
    sample();
  } else {
    window.addEventListener('load', sample);
  }
  setInterval(sample, 30000);
})();
