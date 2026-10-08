// DOM probe for the kiosk page's applied state, read back through the
// window title (surf has no other exfiltration channel). Evaluated by surf
// once per finished load and every 5 s after. No network, no storage, no
// timer beyond the one interval. No field here ever carries config.json or
// kiosk.conf content: diag/rem report a static string's length, never its
// text; configuration-error/layout/modules report a classification, a
// geometry verdict and counts, never file bytes.
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

  function textLength(selector) {
    var el = document.querySelector(selector);
    return el ? el.textContent.length : 0;
  }

  function configurationError() {
    var el = document.querySelector('[data-configuration-error]');
    return el ? el.getAttribute('data-configuration-error') : null;
  }

  function regionElements() {
    return document.querySelectorAll('[data-region]');
  }

  function overlaps(a, b) {
    return !(a.bottom <= b.top || a.top >= b.bottom || a.right <= b.left || a.left >= b.right);
  }

  function layoutField() {
    var band = document.querySelector('[data-backend-unreachable]');
    if (!band) {
      return '';
    }
    var bandRect = band.getBoundingClientRect();
    var regions = regionElements();
    var overlapId = null;
    for (var i = 0; i < regions.length; i++) {
      if (overlaps(regions[i].getBoundingClientRect(), bandRect)) {
        overlapId = regions[i].getAttribute('data-region');
        break;
      }
    }
    var tag = overlapId ? 'overlap:' + overlapId : 'clear';
    return ' layout=' + window.innerWidth + 'x' + window.innerHeight + ':' + tag;
  }

  function report() {
    var faulted = document.querySelectorAll('[data-module-unavailable]').length;
    var loading = document.querySelectorAll('[data-module-loading]').length;
    var unreachable = document.querySelector('[data-backend-unreachable]') ? 1 : 0;
    var cfgError = configurationError();

    var title = 'WK1 nonce=' + performance.timeOrigin +
      ' state=' + state() +
      ' cards=-/-' +
      ' faulted=' + faulted +
      ' unreachable=' + unreachable +
      ' diag=' + textLength('[data-diagnosis]') +
      ' rem=' + textLength('[data-remediation]') +
      ' modules=' + faulted + '/' + loading;
    if (cfgError !== null) {
      title += ' configuration-error=' + cfgError;
    }
    title += layoutField();

    document.title = title;
  }

  report();
  setInterval(report, 5000);
})();
