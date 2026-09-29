(function () {
try {
  var T0 = performance.now(), last = T0, n = 0;
  var WARM = 40000, SETTLE = 4000, MEAS = 12000;

  // Each phase: hide the app or not, and drive a synthetic damage rect of a
  // known size at a known rate. Area and update-rate are varied independently,
  // which is what separates "cost is proportional to damaged area" from
  // "cost is a fixed per-frame present".
  var PH = [
    { id: 'b0', hide: false, w: 0, h: 0, every: 0 },
    { id: 'Q1', hide: true, w: 0, h: 0, every: 0 },
    { id: 'Q2', hide: true, w: 40, h: 40, every: 1 },
    { id: 'Q3', hide: true, w: 1920, h: 270, every: 1 },
    { id: 'Q4', hide: true, w: 1920, h: 270, every: 8 },
    { id: 'b1', hide: false, w: 0, h: 0, every: 0 }
  ];

  var pi = -1, state = 'warm', tmark = T0;
  var wi = [], ti = [], out = [], upd = 0;

  var box = document.createElement('div');
  box.id = 'pwtprobe';
  box.style.setProperty('position', 'fixed', 'important');
  box.style.setProperty('left', '0px', 'important');
  box.style.setProperty('top', '300px', 'important');
  box.style.setProperty('background', '#888', 'important');
  box.style.setProperty('z-index', '2147483647', 'important');
  box.style.setProperty('display', 'none', 'important');

  function q(sel) { try { return document.querySelectorAll(sel); } catch (e) { return []; } }
  function appEl() { return document.getElementById('app'); }

  function cs(el, prop) {
    var v = getComputedStyle(el).getPropertyValue(prop);
    return (v === '' ? '-' : v).replace(/\s+/g, '_');
  }

  function setup(p) {
    var a = appEl();
    if (a) {
      if (p.hide) a.style.setProperty('display', 'none', 'important');
      else a.style.removeProperty('display');
    }
    if (p.w) {
      box.style.setProperty('width', p.w + 'px', 'important');
      box.style.setProperty('height', p.h + 'px', 'important');
      box.style.setProperty('display', 'block', 'important');
    } else {
      box.style.setProperty('display', 'none', 'important');
    }
    upd = 0;
  }

  function verify(p) {
    var a = appEl();
    var ad = a ? cs(a, 'display') : 'NOAPP';
    var bd = cs(box, 'display');
    var bw = Math.round(box.getBoundingClientRect().width);
    var bh = Math.round(box.getBoundingClientRect().height);
    return 'app.display=' + ad + ',box=' + bd + ':' + bw + 'x' + bh + ',upd=' + upd;
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

  function step() {
    var now = performance.now(), d = now - last;
    last = now; n++;
    if (state === 'meas') wi.push(d);

    var p = (pi >= 0 && pi < PH.length) ? PH[pi] : null;
    if (p && p.every && (state === 'meas' || state === 'settle')) {
      if (n % p.every === 0) {
        box.style.setProperty('transform', 'translateY(' + ((n / p.every) % 2 ? 9 : 0) + 'px)', 'important');
        if (state === 'meas') upd++;
      }
    }

    if (state === 'warm') {
      if (now - T0 >= WARM && q('.card').length > 0) {
        if (!box.parentNode) document.body.appendChild(box);
        pi = 0; state = 'settle'; tmark = now; setup(PH[0]);
      }
    } else if (state === 'settle') {
      if (now - tmark >= SETTLE) { state = 'meas'; tmark = now; wi = []; ti = []; upd = 0; }
    } else if (state === 'meas') {
      if (now - tmark >= MEAS) {
        stats(PH[pi], Math.round((tmark - T0) / 1000));
        if (pi + 1 >= PH.length) {
          var a = appEl(); if (a) a.style.removeProperty('display');
          box.style.setProperty('display', 'none', 'important');
          if (box.parentNode) box.parentNode.removeChild(box);
          state = 'done';
        } else { pi++; state = 'settle'; tmark = now; setup(PH[pi]); }
      }
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);

  setInterval(function () {
    var t = Math.round((performance.now() - T0) / 1000);
    document.title = 'EX3 s' + t + ' st=' + state + ' ph=' + (pi >= 0 && pi < PH.length ? PH[pi].id : '-') +
      ' app[all=' + document.querySelectorAll('*').length + ',card=' + q('.card').length + ']' +
      ' R{' + out.join(';') + '}';
  }, 3000);
} catch (e) { document.title = 'EX3 ERR ' + e; }
})();
