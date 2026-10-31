#!/usr/bin/env python3
"""Final-window [stats] reduction for the #245 batch-2 run-14 reset, plus the same
elapsed-time window in each healthy batch-2 run (per run, never blended).

Usage: reset2_window.py <summary.txt> [--dump RECORD]
Read-only: reads records under ~/meta-wisekiosk/records, writes nothing.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path.home() / "meta-wisekiosk"
LINE_RE = re.compile(r"^(\S+) \[(\w+)\] (.*)$")
STATS_RE = re.compile(
    r"^MemFree:(\d+) Dirty:(\d+) Writeback:(\d+) load=([\d.]+) [\d.]+ [\d.]+ mmc=([\d ]+) uv=(\d+)$")
START_RE = re.compile(r"^(\S+) capture started$", re.M)
# reset run: last [stats] sample is 138.93 s after capture started; window is the 60 s before it
WIN_END, WIN_LEN = 138.93, 60.0


def capture(record):
    for line in (REPO / "records" / record / "report.jsonl").open():
        d = json.loads(line)
        if d.get("when") != "setup":
            continue
        s = dict(d.get("sections", []))
        if "Captured stdout setup" in s and "capture started" in s.get("Captured stderr setup", ""):
            return s["Captured stdout setup"], s["Captured stderr setup"]
    return None, None


def samples(stdout):
    out = []
    for line in stdout.splitlines():
        m = LINE_RE.match(line)
        if not m or m.group(2) != "stats":
            continue
        sm = STATS_RE.match(m.group(3))
        if not sm:
            continue
        mmc = [int(x) for x in sm.group(5).split()]
        out.append(dict(t=datetime.fromisoformat(m.group(1)), memfree=int(sm.group(1)),
                        dirty=int(sm.group(2)), wb=int(sm.group(3)), load=float(sm.group(4)),
                        wsec=mmc[6], inflight=mmc[8], ioticks=mmc[9], uv=int(sm.group(6)), line=line))
    return out


def reduce(ss, t0, lo, hi):
    w = [s for s in ss if lo <= (s["t"] - t0).total_seconds() <= hi]
    rates, gaps, zero = [], [], 0
    longest_zero = 0.0
    for a, b in zip(w, w[1:]):
        dt = (b["t"] - a["t"]).total_seconds()
        gaps.append(dt)
        if dt < 0.5:
            continue
        dw = b["wsec"] - a["wsec"]
        rates.append(dw * 512 / dt / 1e6)
        zero = zero + dt if dw == 0 else 0.0
        longest_zero = max(longest_zero, zero)
    return dict(n=len(w), memfree=(min(s["memfree"] for s in w), max(s["memfree"] for s in w)),
                dirty=max(s["dirty"] for s in w), wb=max(s["wb"] for s in w),
                load=max(s["load"] for s in w), rate=(min(rates), sum(rates) / len(rates), max(rates)),
                inflight=max(s["inflight"] for s in w), uv=max(s["uv"] for s in w),
                gap=(min(gaps), max(gaps)), zero=longest_zero, w=w)


def main():
    summary = Path(sys.argv[1])
    dump = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--dump" else None
    for line in summary.read_text().splitlines():
        rec = re.search(r"record=records/(\S+)", line).group(1)
        run = re.search(r"run=(\d+)", line).group(1)
        reset = "reset=yes" in line
        so, se = capture(rec)
        t0 = datetime.fromisoformat(START_RE.search(se).group(1))
        ss = samples(so)
        r = reduce(ss, t0, WIN_END - WIN_LEN, WIN_END)
        print(f"run={run} rec={rec} reset={'yes' if reset else 'no'} n={r['n']} "
              f"MemFree={r['memfree'][0]}..{r['memfree'][1]} maxDirty={r['dirty']} maxWB={r['wb']} "
              f"maxload={r['load']:.2f} wMB/s min/mean/max={r['rate'][0]:.2f}/{r['rate'][1]:.2f}/{r['rate'][2]:.2f} "
              f"maxinflight={r['inflight']} uv={r['uv']} gap={r['gap'][0]:.2f}..{r['gap'][1]:.2f} "
              f"longest0write={r['zero']:.1f}")
        if dump == rec:
            prev = None
            for s in r["w"]:
                d = "" if prev is None else (
                    f" dt={(s['t'] - prev['t']).total_seconds():.3f} dW={s['wsec'] - prev['wsec']}"
                    f" ({(s['wsec'] - prev['wsec']) * 512 / (s['t'] - prev['t']).total_seconds() / 1e6:.2f} MB/s)"
                    f" dIOticks={s['ioticks'] - prev['ioticks']}")
                print(f"  {s['t'].isoformat()} MemFree={s['memfree']} Dirty={s['dirty']} WB={s['wb']} "
                      f"load={s['load']} inflight={s['inflight']} uv={s['uv']}{d}")
                prev = s


if __name__ == "__main__":
    main()
