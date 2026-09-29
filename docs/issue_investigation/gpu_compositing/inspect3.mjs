// Drive the WebKit remote inspector over an SSH tunnel on 127.0.0.1:2999.
//
//   node inspect3.mjs fps <arm_seconds>   delivered frame rate, from rAF timestamps
//   node inspect3.mjs eval '<js>'         evaluate one expression, print the result
//
// Two things differ from a Chrome CDP endpoint and both are load-bearing:
//   * the target list is HTML at /, not JSON at /json/list; the Inspect button
//     carries the WebSocket path.
//   * every CDP call is wrapped in Target.sendMessageToTarget and every reply
//     arrives as a Target.dispatchMessageFromTarget event, so ids must be
//     matched on the INNER message, not the outer one.

const PORT = 2999;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function target() {
	const res = await fetch(`http://127.0.0.1:${PORT}/`);
	if (!res.ok) throw new Error(`/ -> HTTP ${res.status}`);
	const html = await res.text();
	const m = html.match(/ws=' \+ window\.location\.host \+ '([^']+)'/);
	if (!m) throw new Error(`no socket path in target list: ${html.slice(0, 400)}`);
	const name = (html.match(/class="targeturl">([^<]*)</) || [])[1] || '?';
	return { url: name, ws: `ws://127.0.0.1:${PORT}${m[1]}` };
}

function connect(url) {
	const ws = new WebSocket(url);
	const pending = new Map();
	let next = 1;
	let targetId = null;
	let onTarget;
	const gotTarget = new Promise((r) => (onTarget = r));
	const ready = new Promise((ok, fail) => {
		ws.addEventListener('open', () => ok());
		ws.addEventListener('error', (e) => fail(new Error(`ws error: ${e.message ?? e}`)));
	});

	const settle = (inner) => {
		const p = pending.get(inner.id);
		if (!p) return;
		pending.delete(inner.id);
		inner.error ? p.fail(new Error(JSON.stringify(inner.error))) : p.ok(inner.result);
	};

	ws.addEventListener('message', (ev) => {
		let msg;
		try {
			msg = JSON.parse(ev.data);
		} catch {
			return;
		}
		if (msg.method === 'Target.targetCreated') {
			targetId = msg.params?.targetInfo?.targetId;
			onTarget(targetId);
			return;
		}
		if (msg.method === 'Target.dispatchMessageFromTarget') {
			try {
				settle(JSON.parse(msg.params.message));
			} catch {}
			return;
		}
		if (msg.id !== undefined) settle(msg);
	});

	const send = (method, params = {}) =>
		new Promise((ok, fail) => {
			const id = next++;
			pending.set(id, { ok, fail });
			const inner = JSON.stringify({ id, method, params });
			ws.send(
				JSON.stringify({
					id: 100000 + id,
					method: 'Target.sendMessageToTarget',
					params: { targetId, message: inner },
				}),
			);
			setTimeout(() => {
				if (pending.delete(id)) fail(new Error(`${method} timed out`));
			}, 30000);
		});

	return { ready, gotTarget, send, close: () => ws.close(), tid: () => targetId };
}

async function evaluate(c, expression) {
	const r = await c.send('Runtime.evaluate', { expression, returnByValue: true });
	if (r.wasThrown) throw new Error(`threw: ${JSON.stringify(r.result)}`);
	return r.result?.value;
}

// Arm and read are separate evaluates so the collection window runs with no
// protocol traffic in flight -- the inspector must not pay for the frames it counts.
const PROBE = `(() => {
  window.__fr = [];
  if (window.__frID) cancelAnimationFrame(window.__frID);
  const tick = (t) => { window.__fr.push(t); window.__frID = requestAnimationFrame(tick); };
  window.__frID = requestAnimationFrame(tick);
  return 'armed';
})()`;

const READ = `(() => {
  const t = window.__fr || [];
  if (window.__frID) cancelAnimationFrame(window.__frID);
  const d = [];
  for (let i = 1; i < t.length; i++) d.push(t[i] - t[i-1]);
  const sorted = d.slice().sort((a,b) => a-b);
  const at = (p) => sorted.length ? sorted[Math.min(sorted.length-1, Math.floor(sorted.length*p))] : 0;
  const span = t.length > 1 ? (t[t.length-1] - t[0]) / 1000 : 0;
  return JSON.stringify({
    frames: t.length,
    seconds: +span.toFixed(2),
    fps: span > 0 ? +((t.length - 1) / span).toFixed(3) : 0,
    ms_mean: d.length ? +(d.reduce((a,b)=>a+b,0)/d.length).toFixed(1) : 0,
    ms_p50: +at(0.50).toFixed(1),
    ms_p90: +at(0.90).toFixed(1),
    ms_max: +at(1.00).toFixed(1),
  });
})()`;

const [mode, arg] = process.argv.slice(2);
const t = await target();
const c = connect(t.ws);
await c.ready;
await Promise.race([c.gotTarget, sleep(5000)]);
if (!c.tid()) throw new Error('no targetId announced by the inspector');
console.error(`target: ${t.url}  tid=${c.tid()}`);

if (mode === 'fps') {
	const secs = Number(arg ?? 30);
	await evaluate(c, PROBE);
	await sleep(secs * 1000);
	console.log(await evaluate(c, READ));
} else if (mode === 'eval') {
	console.log(JSON.stringify(await evaluate(c, arg)));
} else {
	console.error('usage: inspect3.mjs fps [seconds] | eval <js>');
	process.exitCode = 2;
}
c.close();
