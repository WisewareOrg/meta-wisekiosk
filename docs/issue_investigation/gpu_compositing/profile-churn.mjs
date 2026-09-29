// Name what the app promotes over a window, using the inspector. Heap.startTracking suppresses
// collection (keeps allocations alive), so two raw snapshots (NO forced GC) across the window show
// the accumulation itself -- the churn that paces the full GC -- by class. Run over ~30s = ~4
// rotation ticks to catch the rotation's contribution.  node profile-churn.mjs <seconds>
const PORT = Number(process.env.WEBKIT_INSPECT_PORT || 2999);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function targetWs() {
  const res = await fetch(`http://127.0.0.1:${PORT}/`, { signal: AbortSignal.timeout(10000) });
  const html = await res.text();
  const m = html.match(/ws=' \+ window\.location\.host \+ '([^']+)'/);
  return `ws://127.0.0.1:${PORT}${m[1]}`;
}
function connect(url) {
  const ws = new WebSocket(url); const pending = new Map();
  let next = 1, targetId = null, onTarget; const gotTarget = new Promise((r) => (onTarget = r));
  const ready = new Promise((ok, fail) => { ws.addEventListener('open', () => ok()); ws.addEventListener('error', (e) => fail(new Error(String(e.message ?? e)))); });
  const settle = (i) => { const p = pending.get(i.id); if (p) { pending.delete(i.id); i.error ? p.fail(new Error(JSON.stringify(i.error))) : p.ok(i.result); } };
  ws.addEventListener('message', (ev) => { let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (m.method === 'Target.targetCreated') { targetId = m.params?.targetInfo?.targetId; onTarget(targetId); return; }
    if (m.method === 'Target.dispatchMessageFromTarget') { try { settle(JSON.parse(m.params.message)); } catch {} return; }
    if (m.id !== undefined) settle(m); });
  const send = (method, params = {}) => new Promise((ok, fail) => { const id = next++; pending.set(id, { ok, fail });
    ws.send(JSON.stringify({ id: 100000 + id, method: 'Target.sendMessageToTarget', params: { targetId, message: JSON.stringify({ id, method, params }) } }));
    setTimeout(() => { if (pending.delete(id)) fail(new Error(`${method} timed out`)); }, 60000); });
  return { ready, gotTarget, send, close: () => ws.close(), tid: () => targetId };
}
function census(data) { const { nodes, nodeClassNames } = data; const c = new Map();
  for (let i = 0; i < nodes.length; i += 4) { const cl = nodeClassNames[nodes[i + 2]], s = nodes[i + 1];
    const e = c.get(cl) || { count: 0, size: 0 }; e.count++; e.size += s; c.set(cl, e); } return c; }
async function rawSnap(c) { const s = await c.send('Heap.snapshot'); const r = s.snapshotData ?? s.snapshot ?? s; return census(typeof r === 'string' ? JSON.parse(r) : r); }

const secs = Number(process.argv[2] ?? 30);
const c = connect(await targetWs()); await c.ready; await Promise.race([c.gotTarget, sleep(5000)]);
console.error(`connected tid=${c.tid()}`);
await c.send('Heap.enable');
await c.send('Heap.startTracking');           // suppress collection so accumulation is visible
await sleep(3000);
const a = await rawSnap(c);                    // t0 (no forced GC)
console.error(`baseline; accumulating ${secs}s...`);
await sleep(secs * 1000);
const b = await rawSnap(c);                    // t1 (no forced GC)
await c.send('Heap.stopTracking').catch(() => {});
const rows = [];
for (const [cls, e] of b) { const w = a.get(cls) || { count: 0, size: 0 }; rows.push({ cls, dCount: e.count - w.count, dSize: e.size - w.size }); }
rows.sort((x, y) => y.dCount - x.dCount);
console.log(`accumulation over ${secs}s (GC suppressed), by object count:`);
console.log(`${'Δcount'.padStart(8)} ${'Δbytes'.padStart(10)}  class`);
for (const r of rows.slice(0, 16)) if (r.dCount > 0) console.log(`${String(r.dCount).padStart(8)} ${String(r.dSize).padStart(10)}  ${r.cls}`);
c.close(); process.exit(0);
