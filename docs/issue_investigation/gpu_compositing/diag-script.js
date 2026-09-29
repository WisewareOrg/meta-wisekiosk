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
