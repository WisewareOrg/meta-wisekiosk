#!/usr/bin/env python3
"""Feasible range of the watchdog's tick scale k (hardware seconds -> uptime
seconds) given hb245 readings: with scale k a reading w at t means
t - k(14-w) <= P < t - k(13-w). A k is feasible for a run if every group of
samples sharing a pet has a non-empty intersection. Read-only."""
import json, re, sys
from datetime import datetime
HB = re.compile(r"^\S+ \[kernel\] (\S+) hb245 (\S+) .* wdt=(\d+) ")
def sec(rec):
    for line in open(f"{rec}/report.jsonl"):
        d = json.loads(line)
        if d.get("$report_type") == "TestReport" and d.get("when") == "setup":
            s = dict(d.get("sections", []))
            if "capture started" in s.get("Captured stderr setup", ""):
                return s.get("Captured stdout setup", "")
DELTA = float(__import__("os").environ["DELTA"])
runs = []
for rec in sys.argv[1:]:
    rows = []
    for l in sec(rec).splitlines():
        m = HB.match(l)
        if m:
            b = datetime.fromisoformat(m.group(1).replace(",", ".")).timestamp()
            rows.append((float(m.group(2)), b, int(m.group(3))))
    base = min(b - u for u, b, w in rows)
    runs.append([(u, b - base, w) for u, b, w in rows])
def feasible(k):
    for rows in runs:
        pw = None; lo = hi = None
        for u, pk, w in rows:
            l, h = u - k * (14 - w), pk + DELTA - k * (13 - w)
            if pw is not None and w <= pw:
                lo, hi = max(lo, l), min(hi, h)
                if hi < lo:
                    return False
            else:
                lo, hi = l, h
            pw = w
    return True
ks = [round(0.90 + i * 0.001, 3) for i in range(201)]
ok = [k for k in ks if feasible(k)]
print("feasible k range", ok[0] if ok else None, ok[-1] if ok else None, "count", len(ok))
