(function () {
  if (window.__cp) return;
  window.__cp = 1;

  // Cards-live probe: a card is [data-pwt-card]; it holds live data when it also contains
  // [data-pwt-leaderboard]. A closed card carries [data-pwt-closed], a per-park API failure
  // [data-pwt-unavailable] -- neither of those is checked here, only whether the leaderboard
  // actually rendered. Logs via console.log (not document.title, so this runs alongside a
  // title-based probe without clobbering it), read from the kiosk journal under
  // --enable-write-console-messages-to-stdout=true (bundled with KIOSK_PROBE=1).
  // Payload: parse_cards_probe.py's header. c = card count, l = leaderboard count; the gate is
  // c=4 l=4.
  function sample() {
    var c = document.querySelectorAll('[data-pwt-card]').length;
    var l = document.querySelectorAll('[data-pwt-card] [data-pwt-leaderboard]').length;
    console.log('CP|t=' + Math.round(performance.now() / 1000) + '|c=' + c + '|l=' + l);
  }

  if (document.readyState === 'complete') {
    sample();
  } else {
    window.addEventListener('load', sample);
  }
  setInterval(sample, 30000);
})();
