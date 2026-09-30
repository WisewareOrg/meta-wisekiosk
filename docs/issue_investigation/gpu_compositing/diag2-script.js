(function () {
try {
  var E = '', C = '';
  window.addEventListener('error', function (e) {
    if (E.length < 120) E += '|' + ((e.message || '?') + '@' + String(e.filename || '').split('/').pop() + ':' + e.lineno);
  }, true);
  window.addEventListener('unhandledrejection', function (e) {
    if (E.length < 120) E += '|REJ:' + String(e.reason).slice(0, 60);
  }, true);
  document.addEventListener('securitypolicyviolation', function (e) {
    if (C.length < 120) C += '|' + e.violatedDirective + ':' + String(e.blockedURI || '').slice(-30);
  }, true);
  window.onerror = function (m, f, l) { if (E.length < 200) E += '|ONERR:' + String(m).slice(0, 80) + '@' + String(f || '').split('/').pop() + ':' + l; };
  setTimeout(function () {
    var sc = document.querySelector('script[type=module]');
    var src = sc ? sc.getAttribute('src') : null;
    if (!src) { E += '|NOSCRIPTTAG'; return; }
    fetch(src).then(function (r) { E += '|FETCH' + r.status + ':' + r.headers.get('content-type'); return r.text(); })
      .then(function (t) { E += ':len' + t.length; })
      .catch(function (e) { E += '|FETCHFAIL:' + String(e && e.message || e).slice(0, 60); });
    import(src).then(function () { E += '|IMPORT_OK'; },
      function (e) { E += '|IMPORT_FAIL:' + String(e && e.message || e).slice(0, 100); });
  }, 8000);
  setInterval(function () {
    var b = document.body;
    document.title = 'DIAG rs=' + document.readyState +
      ' all=' + document.querySelectorAll('*').length +
      ' card=' + document.querySelectorAll('.card').length +
      ' mq=' + document.querySelectorAll('.marquee').length +
      ' ss=' + document.styleSheets.length +
      ' bg=' + (b ? getComputedStyle(b).backgroundColor.replace(/[ ()]/g, '') : '-') +
      ' bh=' + (b ? Math.round(b.getBoundingClientRect().height) : -1) +
      ' vis=' + document.visibilityState +
      ' E[' + E + '] C[' + C + ']';
  }, 3000);
} catch (e) { document.title = 'DIAG ERR ' + e; }
})();
