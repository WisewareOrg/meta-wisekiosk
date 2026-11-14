// In-page probe for the kiosk page. surf has no channel out of a page but the
// window title, so the probe writes its report there; the host reads it back
// through xprop. Evaluated by surf in every page load. No network, no storage.
// Payload: "WK1 " then key=value tokens. nonce is performance.timeOrigin (new
// per page load); state is the app's own state; cards is <present>/<live>.
(function () {
  if (window.__wk1) { return; }
  window.__wk1 = true;

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

  function report() {
    var title = 'WK1 nonce=' + performance.timeOrigin +
      ' state=' + state() +
      ' cards=' + cards() +
      ' origin=' + location.origin;
    if (document.title !== title) { document.title = title; }
  }

  report();
  setInterval(report, 1000);
})();
