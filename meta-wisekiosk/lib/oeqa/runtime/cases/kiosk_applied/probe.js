// DOM probe for the kiosk page's applied state, read back through the
// window title (surf has no other exfiltration channel). Evaluated by surf
// once per finished load and every 5 s after. No network, no storage, no
// timer beyond the one interval.
(function () {
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

  // present is every [data-pwt-card]/[data-pwt-leaderboard] element; live
  // is the subset holding at least one [data-pwt-tour-row] descendant.
  function cards() {
    var all = document.querySelectorAll('[data-pwt-card], [data-pwt-leaderboard]');
    var live = 0;
    for (var i = 0; i < all.length; i++) {
      if (all[i].querySelector('[data-pwt-tour-row]')) live++;
    }
    return all.length + '/' + live;
  }

  function report() {
    var faulted = document.querySelectorAll('[data-module-unavailable]').length;
    var unreachable = document.querySelector('[data-backend-unreachable]') ? 1 : 0;
    document.title = 'WK1 nonce=' + performance.timeOrigin +
      ' state=' + state() +
      ' cards=' + cards() +
      ' faulted=' + faulted +
      ' unreachable=' + unreachable;
  }

  report();
  setInterval(report, 5000);
})();
