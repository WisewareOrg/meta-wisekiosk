(function () {
try {
  var T0 = performance.now(), last = T0, n = 0;
  var WARM = 40000, SETTLE = 4000, MEAS = 12000;

  // Each phase sets zero or more declarations on .seconds and on its parent (.annotations).
  // The candidate fix needs `position:relative` on the parent, so a phase is a pair of lists.
  // C1 is the positive control: the prior session measured .seconds{display:none} at ~3x, so a
  // run in which C1 does not move is a run whose nulls mean nothing.
  var PH = [
    { id: 'b0', el: [], par: [] },
    { id: 'F1', el: [['position','absolute'],['top','0px'],['left','0px'],['contain','size layout'],['width','53px'],['height','34.5625px']], par: [['position','relative']] },
    { id: 'b1', el: [], par: [] },
    { id: 'F2', el: [['position','absolute'],['top','0px'],['left','0px'],['contain','strict'],['width','53px'],['height','34.5625px']], par: [['position','relative']] },
    { id: 'b2', el: [], par: [] },
    { id: 'C1', el: [['display','none']], par: [] },
    { id: 'b3', el: [], par: [] },
    { id: 'F1b', el: [['position','absolute'],['top','0px'],['left','0px'],['contain','size layout'],['width','53px'],['height','34.5625px']], par: [['position','relative']] },
    { id: 'b4', el: [], par: [] }
  ];

  var ALLPROP = ['position','top','left','contain','width','height','display'];
  var SEL = '.seconds';

  var pi = -1, state = 'warm', tmark = T0, lastApply = 0;
  var wi = [], ti = [], out = [], pre = '?', found = 0, cg0 = '', cgBad = 0;

  function q(sel) { try { return document.querySelectorAll(sel); } catch (e) { return []; } }

  function clearAll() {
    var els = q(SEL), i, k;
    for (i = 0; i < els.length; i++) {
      for (k = 0; k < ALLPROP.length; k++) els[i].style.removeProperty(ALLPROP[k]);
      els[i].__phid = null;
      if (els[i].parentElement) els[i].parentElement.style.removeProperty('position');
    }
  }

  function apply(p) {
    var els = q(SEL), i, k;
    found = els.length;
    if (!p.el.length && !p.par.length) return;
    for (i = 0; i < els.length; i++) {
      if (els[i].__phid === p.id) continue;
      for (k = 0; k < p.el.length; k++) els[i].style.setProperty(p.el[k][0], p.el[k][1], 'important');
      if (els[i].parentElement) {
        for (k = 0; k < p.par.length; k++) els[i].parentElement.style.setProperty(p.par[k][0], p.par[k][1], 'important');
      }
      els[i].__phid = p.id;
    }
  }

  // computed signature: the two properties that decide whether the box is a relayout boundary
  function sig(el) {
    var c = getComputedStyle(el);
    var f = function (v) { return (v === '' ? '-' : v).replace(/\s+/g, '_'); };
    return f(c.getPropertyValue('position')) + ',' + f(c.getPropertyValue('contain')) + ',' + f(c.getPropertyValue('display'));
  }

  function snapPre(p) { var els = q(SEL); pre = els.length ? sig(els[0]) : 'NOELEM'; }

  function verify(p) {
    var els = q(SEL);
    if (!els.length) return 'NOELEM';
    var inl = 0, chg = 0, post = '?', i;
    for (i = 0; i < els.length; i++) {
      if (els[i].__phid === p.id) { inl++; if (post === '?') post = sig(els[i]); if (sig(els[i]) !== pre) chg++; }
    }
    if (!p.el.length && !p.par.length) { post = sig(els[0]); }
    return pre + '>' + post + ':inl' + inl + '/' + els.length + ':chg' + chg;
  }

  // Content guard: parks close through the evening, which relayouts the page for reasons that
  // have nothing to do with the seconds. A window whose card/wait content changed is flagged so
  // it can be dropped rather than read as a seconds result.
  function contentSig() {
    var w = q('.wait'), s = '', i;
    for (i = 0; i < w.length; i++) s += w[i].textContent + '|';
    return q('.card').length + ':' + w.length + ':' + s.length;
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
      cgBad ? 'CONTENTCHANGED' : 'ok',
      vstr
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
    pi = i; state = 'settle'; tmark = now; clearAll();
    snapPre(PH[i]); apply(PH[i]); lastApply = now;
  }

  function step() {
    var now = performance.now(), d = now - last;
    last = now; n++;
    if (state === 'meas') wi.push(d);

    if (state === 'warm') {
      if (now - T0 >= WARM && q('.card').length > 0 && q('.seconds').length > 0) enter(0, now);
    } else if (state === 'settle') {
      if (now - lastApply > 2500) { apply(PH[pi]); lastApply = now; }
      if (now - tmark >= SETTLE) { state = 'meas'; tmark = now; wi = []; ti = []; cg0 = contentSig(); cgBad = 0; }
    } else if (state === 'meas') {
      if (now - lastApply > 2500) { apply(PH[pi]); lastApply = now; }
      if (contentSig() !== cg0) cgBad = 1;
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
    document.title = 'EX7 s' + t + ' st=' + state + ' ph=' + (pi >= 0 && pi < PH.length ? PH[pi].id : '-') +
      ' app[all=' + document.querySelectorAll('*').length + ',card=' + q('.card').length +
      ',sec=' + q('.seconds').length + ']' +
      ' R{' + out.join(';') + '}';
  }, 3000);
} catch (e) { document.title = 'EX7 ERR ' + e; }
})();
