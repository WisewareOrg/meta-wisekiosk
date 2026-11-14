// In-page probe for the kiosk page. surf has no channel out of a page but the
// window title, so the probe writes its report there; the host reads it back
// through xprop. Evaluated by surf in every page load. No network, no storage.
// Payload: "WK1 " then key=value tokens. nonce is performance.timeOrigin; state
// is the app's own state; cards is <present>/<live>. Every other token is
// cumulative from the probe's own start in this page load, times in ms of
// performance.now():
//   load    random token drawn once per page load (the page-load identity)
//   el      this title write
//   frames  requestAnimationFrame intervals counted
//   isum    the sum of those intervals
//   hist    7 bins of those intervals: <50, 50-100, 100-250, 250-500,
//           500-1000, 1000-2000, >=2000
//   changes transitions of the pair (state, cards), counted at each report
//   ticks   report ticks
//   moving  ticks at which some [data-marquee] element's parent had
//           scrollLeft > 0
//   cost    the probe's own callback time
(function () {
  if (window.__wk1) { return; }
  window.__wk1 = true;

  var load = Math.random().toString(36).slice(2, 10);
  var EDGES = [50, 100, 250, 500, 1000, 2000];
  var hist = [0, 0, 0, 0, 0, 0, 0];
  var frames = 0, isum = 0, cost = 0, prev = -1;
  var stateKey = null, changes = 0, ticks = 0, moving = 0;

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

  // One interval per frame: count, sum, histogram.
  function tick(now) {
    var begin = performance.now();
    if (prev >= 0) {
      var dt = now - prev;
      frames++;
      isum += dt;
      var b = 0;
      while (b < EDGES.length && dt >= EDGES[b]) { b++; }
      hist[b]++;
    }
    prev = now;
    requestAnimationFrame(tick);
    cost += performance.now() - begin;
  }

  function scrolling() {
    var marquees = document.querySelectorAll('[data-marquee]');
    for (var i = 0; i < marquees.length; i++) {
      var parent = marquees[i].parentElement;
      if (parent && parent.scrollLeft > 0) { return true; }
    }
    return false;
  }

  function report() {
    var begin = performance.now();
    var shown = state();
    var count = cards();
    var tuple = shown + ' ' + count;
    if (tuple !== stateKey) {
      stateKey = tuple;
      changes++;
    }
    ticks++;
    if (scrolling()) { moving++; }
    var title = 'WK1 nonce=' + performance.timeOrigin +
      ' state=' + shown +
      ' cards=' + count +
      ' origin=' + location.origin +
      ' load=' + load +
      ' el=' + Math.round(begin) +
      ' frames=' + frames +
      ' isum=' + Math.round(isum) +
      ' hist=' + hist.join(',') +
      ' changes=' + changes +
      ' ticks=' + ticks +
      ' moving=' + moving +
      ' cost=' + Math.round(cost);
    if (document.title !== title) { document.title = title; }
    cost += performance.now() - begin;
  }

  requestAnimationFrame(tick);
  report();
  setInterval(report, 1000);
})();
