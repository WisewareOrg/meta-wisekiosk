// DOM probe for the kiosk page, read back through the window title (surf
// has no other exfiltration channel). Evaluated by surf once per finished
// load; its own timers are the 5 s title write and one rAF chain. No
// network, no storage. Payload: "WK1 " then key=value tokens; times are ms
// of performance.now(), "-" is not yet, counters are cumulative from t0.
// nonce is performance.timeOrigin; el is this write; ttp is when the page
// last entered its full state; frames, isum, bt (>250 ms) and hist count
// frame intervals; cost is the probe's own callback time.
(function () {
  if (window.__wk1) { return; }
  window.__wk1 = true;

  var t0 = performance.now();
  var WARMUP = 15000;
  var EDGES = [50, 100, 250, 500, 1000, 2000];
  var hist = [0, 0, 0, 0, 0, 0, 0];
  var frames = 0, isum = 0, maxstall = 0, bt = 0, cost = 0, prev = -1;
  var fullKey = null, ttpAt = -1, stateKey = null, changes = 0;

  function state() {
    if (document.querySelector('[data-configuration-error]')) {
      return 'error:configuration';
    }
    if (document.querySelector('[data-state="loading"]')) {
      return 'loading';
    }
    if (!document.querySelector('[data-frame]')) {
      return 'error:not-app';
    }
    return 'applied';
  }

  // present is every [data-pwt-card]; live is each card holding a
  // [data-pwt-leaderboard].
  function cards() {
    var all = document.querySelectorAll('[data-pwt-card]');
    var live = 0;
    for (var i = 0; i < all.length; i++) {
      if (all[i].querySelector('[data-pwt-leaderboard]')) { live++; }
    }
    return all.length + '/' + live;
  }

  // One interval per frame: count, sum, longest after WARMUP, >250 ms
  // count, histogram.
  function tick(now) {
    var begin = performance.now();
    if (prev >= 0) {
      var dt = now - prev;
      frames++;
      isum += dt;
      if (now - t0 >= WARMUP && dt > maxstall) { maxstall = dt; }
      if (dt > 250) { bt++; }
      var b = 0;
      while (b < EDGES.length && dt >= EDGES[b]) { b++; }
      hist[b]++;
    }
    prev = now;
    requestAnimationFrame(tick);
    cost += performance.now() - begin;
  }

  function ms(value) {
    return value < 0 ? '-' : String(Math.round(value));
  }

  function report() {
    var begin = performance.now();
    var shown = state();
    var count = cards();
    var full = shown === 'applied' && document.querySelector('[data-weather-present]');
    var key = full ? count : null;
    if (key !== fullKey) {
      fullKey = key;
      ttpAt = full ? begin : -1;
    }
    var faulted = document.querySelectorAll('[data-module-unavailable]').length;
    var unreachable = document.querySelector('[data-backend-unreachable]') ? 1 : 0;
    // changes counts every transition of (state, cards, faulted, unreachable).
    var tuple = shown + ' ' + count + ' ' + faulted + ' ' + unreachable;
    if (tuple !== stateKey) {
      stateKey = tuple;
      changes++;
    }
    document.title = 'WK1 nonce=' + performance.timeOrigin +
      ' state=' + shown +
      ' cards=' + count +
      ' faulted=' + faulted +
      ' unreachable=' + unreachable +
      ' t0=' + ms(t0) +
      ' el=' + ms(begin) +
      ' ttp=' + ms(ttpAt) +
      ' changes=' + changes +
      ' frames=' + frames +
      ' isum=' + ms(isum) +
      ' maxstall=' + ms(maxstall) +
      ' bt=' + bt +
      ' hist=' + hist.join(',') +
      ' cost=' + ms(cost);
    cost += performance.now() - begin;
  }

  requestAnimationFrame(tick);
  report();
  setInterval(report, 5000);
})();
