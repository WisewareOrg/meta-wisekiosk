(function () {
  if (window.__ttp) return;
  window.__ttp = 1;

  // Time-to-page beacon: once the present weather glyph has text and the icon face has loaded,
  // sets document.title to "T <epoch_ms>", epoch_ms being the wall clock at that moment.
  // Polled every 200 ms; fires once.
  var t = setInterval(function () {
    var g = document.querySelector('[data-weather-glyph]');
    if (g && g.textContent.trim().length > 0 && document.fonts.check('1em "Weather Icons"')) {
      document.title = 'T ' + Math.round(performance.timeOrigin + performance.now());
      clearInterval(t);
    }
  }, 200);
})();
