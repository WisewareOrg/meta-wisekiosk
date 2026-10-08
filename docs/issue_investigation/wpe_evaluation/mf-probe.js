(function () {
  if (window.__mf) return;
  window.__mf = 1;

  // Module-fault probe: every 30 s, counts the framework's [data-module-faulted] marker and
  // the modules' own [data-module-unavailable], and writes the MF| payload to document.title.
  // Payload: parse_module_fault_test.py's header. fever = distinct faulted regions, keyed by the
  // marker's [data-region] (a marker with none is keyed by itself); it equals distinct faulted
  // modules while each region holds one placement.
  var fmax = 0, fever = 0, umax = 0;
  var seen = new Set();

  setInterval(function () {
    var faulted = document.querySelectorAll('[data-module-faulted]');
    var f = faulted.length;
    var u = document.querySelectorAll('[data-module-unavailable]').length;
    for (var i = 0; i < f; i++) {
      var region = faulted[i].closest('[data-region]');
      seen.add(region ? region.dataset.region : faulted[i]);
    }
    fever = seen.size;
    if (f > fmax) fmax = f;
    if (u > umax) umax = u;
    document.title =
      'MF|t=' + Math.round(performance.now() / 1000) +
      '|f=' + f + '|fmax=' + fmax + '|fever=' + fever +
      '|u=' + u + '|umax=' + umax;
  }, 30000);
})();
