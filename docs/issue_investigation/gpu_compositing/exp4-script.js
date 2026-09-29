(function () {
try {
  var T0 = performance.now(), last = T0, n = 0;
  var WARM = 40000, SETTLE = 3000, MEAS = 10000;

  // Run 3 showed cost tracks damaged area per unit time. So on the real page
  // something damages a large region continuously. Bisect by hiding each
  // top-level section in turn, with a baseline between every one because the
  // baseline drifts by 3x across a run.
  var PH = [], pi = -1, state = 'warm', tmark = T0;
  var wi = [], ti = [], out = [], cur = null;

  function q(sel) { try { return document.querySelectorAll(sel); } catch (e) { return []; } }

  function label(el) {
    var c = (el.className && el.className.baseVal !== undefined) ? el.className.baseVal : (el.className || '');
    c = String(c).split(/\s+/).filter(function (x) { return x && x.indexOf('svelte-') !== 0; }).join('.');
    return (el.tagName.toLowerCase() + (c ? '.' + c : '')).slice(0, 22);
  }

  function build() {
    var app = document.getElementById('app');
    if (!app) return false;
    var root = app;
    while (root.children.length === 1) root = root.children[0];
    var top = [], i, j;
    for (i = 0; i < root.children.length; i++) top.push({ el: root.children[i], path: 's' + i });
    var cand = top.slice();
    for (i = 0; i < top.length && cand.length < 8; i++) {
      var kids = top[i].el.children;
      for (j = 0; j < kids.length && cand.length < 8; j++) cand.push({ el: kids[j], path: top[i].path + '>' + j });
    }
    if (!cand.length) return false;
    PH.push({ id: 'b0', el: null, lab: '-' });
    for (i = 0; i < cand.length; i++) {
      PH.push({ id: 'h' + i, el: cand[i].el, lab: cand[i].path + '=' + label(cand[i].el) });
      PH.push({ id: 'b' + (i + 1), el: null, lab: '-' });
    }
    return true;
  }

  function cs(el, prop) {
    var v = getComputedStyle(el).getPropertyValue(prop);
    return (v === '' ? '-' : v).replace(/\s+/g, '_');
  }

  function clearAll() {
    for (var i = 0; i < PH.length; i++) if (PH[i].el) PH[i].el.style.removeProperty('display');
  }

  function setup(p) {
    clearAll();
    if (p.el) p.el.style.setProperty('display', 'none', 'important');
  }

  function verify(p) {
    if (!p.el) return '-';
    if (!p.el.isConnected) return p.lab + ':DETACHED';
    return p.lab + ':' + cs(p.el, 'display') + ':wasarea' + Math.round(p.area);
  }

  function pc(a, f) { return a.length ? Math.round(a[Math.min(a.length - 1, Math.floor(f * a.length))]) : -1; }

  function stats(p, tstart) {
    var s = wi.slice().sort(function (a, b) { return a - b; });
    var u = ti.slice().sort(function (a, b) { return a - b; });
    var sum = 0, i;
    for (i = 0; i < s.length; i++) sum += s[i];
    out.push([
      p.id, tstart, s.length, pc(s, 0.5), pc(s, 0.9),
      s.length ? (1000 / (sum / s.length)).toFixed(1) : '-',
      pc(u, 0.5), pc(u, 0.9), verify(p)
    ].join('|'));
  }

  var tprev = performance.now();
  function tick() {
    var now = performance.now();
    if (state === 'meas') ti.push(now - tprev - 100);
    tprev = now;
    setTimeout(tick, 100);
  }
  setTimeout(tick, 100);

  function enter(i, now) {
    pi = i; state = 'settle'; tmark = now; cur = PH[i];
    if (cur.el) { var r = cur.el.getBoundingClientRect(); cur.area = Math.round(r.width * r.height / 1000); }
    setup(cur);
  }

  function step() {
    var now = performance.now(), d = now - last;
    last = now; n++;
    if (state === 'meas') wi.push(d);

    if (state === 'warm') {
      if (now - T0 >= WARM && q('.card').length > 0 && build()) enter(0, now);
    } else if (state === 'settle') {
      if (now - tmark >= SETTLE) { state = 'meas'; tmark = now; wi = []; ti = []; }
    } else if (state === 'meas') {
      if (now - tmark >= MEAS) {
        stats(PH[pi], Math.round((tmark - T0) / 1000));
        if (pi + 1 >= PH.length) { clearAll(); state = 'done'; }
        else enter(pi + 1, now);
      }
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);

  setInterval(function () {
    var t = Math.round((performance.now() - T0) / 1000);
    document.title = 'EX4 s' + t + ' st=' + state + ' ph=' + (cur ? cur.id : '-') +
      ' k=' + PH.length + ' R{' + out.join(';') + '}';
  }, 3000);
} catch (e) { document.title = 'EX4 ERR ' + e; }
})();
