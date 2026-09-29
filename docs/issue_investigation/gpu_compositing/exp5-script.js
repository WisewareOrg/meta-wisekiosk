(function () {
try {
  var T0 = performance.now(), last = T0, n = 0;
  var WARM = 40000, SETTLE = 4000, MEAS = 12000;

  var PH = [
    { id: 'b0', sel: null, prop: null, val: null },
    { id: 'S1', sel: '.seconds', prop: 'display', val: 'none' },
    { id: 'b1', sel: null, prop: null, val: null },
    { id: 'S2', sel: '.clock', prop: 'display', val: 'none' },
    { id: 'b2', sel: null, prop: null, val: null },
    { id: 'S3', sel: '.ride-name-text', prop: 'display', val: 'none' },
    { id: 'b3', sel: null, prop: null, val: null },
    { id: 'S4', sel: '.wait', prop: 'display', val: 'none' },
    { id: 'b4', sel: null, prop: null, val: null }
  ];

  var ALLSEL = ['.seconds', '.clock', '.ride-name-text', '.wait'];
  var ALLPROP = ['display'];

  var pi = -1, state = 'warm', tmark = T0, lastApply = 0;
  var wi = [], ti = [], out = [], pre = '?', found = 0;

  function q(sel) { try { return document.querySelectorAll(sel); } catch (e) { return []; } }

  function clearAll() {
    var i, j, k, els;
    for (i = 0; i < ALLSEL.length; i++) {
      els = q(ALLSEL[i]);
      for (j = 0; j < els.length; j++) {
        for (k = 0; k < ALLPROP.length; k++) els[j].style.removeProperty(ALLPROP[k]);
        els[j].__phid = null;
      }
    }
  }

  function apply(p) {
    if (!p.sel) { found = 0; return; }
    var els = q(p.sel), i;
    for (i = 0; i < els.length; i++) {
      if (els[i].__phid !== p.id) { els[i].style.setProperty(p.prop, p.val, 'important'); els[i].__phid = p.id; }
    }
    found = els.length;
  }

  function cs(el, prop) {
    var v = getComputedStyle(el).getPropertyValue(prop);
    return (v === '' ? '-' : v).replace(/\s+/g, '_');
  }

  function snapPre(p) {
    if (!p.sel) { pre = '-'; return; }
    var els = q(p.sel);
    pre = els.length ? cs(els[0], p.prop) : 'NOELEM';
  }

  function verify(p) {
    if (!p.sel) return '-';
    var els = q(p.sel);
    if (!els.length) return 'NOELEM';
    var inl = 0, chg = 0, post = '?', i;
    for (i = 0; i < els.length; i++) {
      if (els[i].__phid === p.id) {
        inl++;
        if (post === '?') post = cs(els[i], p.prop);
        if (cs(els[i], p.prop) !== pre) chg++;
      }
    }
    return p.prop + ':' + pre + '>' + post + ':inl' + inl + '/' + els.length + ':chg' + chg;
  }

  function pc(a, f) { return a.length ? Math.round(a[Math.min(a.length - 1, Math.floor(f * a.length))]) : -1; }

  function stats(p, vstr, tstart) {
    var s = wi.slice().sort(function (a, b) { return a - b; });
    var u = ti.slice().sort(function (a, b) { return a - b; });
    var sum = 0, i;
    for (i = 0; i < s.length; i++) sum += s[i];
    out.push([
      p.id, tstart, s.length,
      pc(s, 0.5), pc(s, 0.9), Math.round(s.length ? s[s.length - 1] : -1),
      s.length ? (1000 / (sum / s.length)).toFixed(1) : '-',
      pc(u, 0.5), pc(u, 0.9),
      found, vstr
    ].join('|'));
  }

  // Timer lateness: a 100 ms self-rescheduling timeout. Large rAF gaps with
  // small lateness means the main thread is free and the wait is downstream.
  var tprev = performance.now();
  function tick() {
    var now = performance.now();
    if (state === 'meas') ti.push(now - tprev - 100);
    tprev = now;
    setTimeout(tick, 100);
  }
  setTimeout(tick, 100);

  function enter(i, now) {
    pi = i; state = 'settle'; tmark = now; clearAll();
    snapPre(PH[i]); apply(PH[i]); lastApply = now;
  }

  function step() {
    var now = performance.now(), d = now - last;
    last = now; n++;
    if (state === 'meas') wi.push(d);

    if (state === 'warm') {
      if (now - T0 >= WARM && q('.card').length > 0 && q('.ride-name').length > 0) enter(0, now);
    } else if (state === 'settle') {
      if (now - lastApply > 2500) { apply(PH[pi]); lastApply = now; }
      if (now - tmark >= SETTLE) { state = 'meas'; tmark = now; wi = []; ti = []; }
    } else if (state === 'meas') {
      if (now - lastApply > 2500) { apply(PH[pi]); lastApply = now; }
      if (now - tmark >= MEAS) {
        stats(PH[pi], verify(PH[pi]), Math.round((tmark - T0) / 1000));
        if (pi + 1 >= PH.length) { clearAll(); state = 'done'; }
        else enter(pi + 1, now);
      }
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);

  setInterval(function () {
    var t = Math.round((performance.now() - T0) / 1000);
    document.title = 'EX5 s' + t + ' st=' + state + ' ph=' + (pi >= 0 && pi < PH.length ? PH[pi].id : '-') +
      ' app[all=' + document.querySelectorAll('*').length + ',card=' + q('.card').length +
      ',mq=' + q('.ride-name-text.marquee').length + ']' +
      ' R{' + out.join(';') + '}';
  }, 3000);
} catch (e) { document.title = 'EX5 ERR ' + e; }
})();
