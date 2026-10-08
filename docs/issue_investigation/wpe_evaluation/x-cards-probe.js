(function () {
  if (window.__cpx) return;
  window.__cpx = 1;

  // X-session variant of cards-probe.js: surf/X has no console-to-journal channel wired up
  // (that's cog's --enable-write-console-messages-to-stdout, WPE-only), so this writes the
  // same c/l payload to document.title instead, read back the same way run-appliance.sh
  // reads p7_min.js's MP| title (xprop -len <n> WM_NAME). Prefix CPX| to stay distinct from
  // MP|/BL| in the same title-reading convention.
  function sample() {
    var c = document.querySelectorAll('[data-pwt-card]').length;
    var l = document.querySelectorAll('[data-pwt-card] [data-pwt-leaderboard]').length;
    document.title = 'CPX|t=' + Math.round(performance.now() / 1000) + '|c=' + c + '|l=' + l;
  }

  if (document.readyState === 'complete') {
    sample();
  } else {
    window.addEventListener('load', sample);
  }
  setInterval(sample, 5000);
})();
