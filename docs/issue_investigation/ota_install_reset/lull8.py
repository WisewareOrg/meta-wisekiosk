#!/usr/bin/env python3
"""Writer-lull check: longest stretch (seconds of uptime) in each record's
install window where Dirty stays within 100 kB of its stretch start while
Writeback > 0 (writer adding nothing, writeback draining). Host [kernel] hb245
lines after 'capture started'; for the reset record pstore's extra last line
is appended. Read-only."""
import json, re, sys
from datetime import datetime
HB = re.compile(r"^\S+ \[kernel\] (\d{4}-\S+) hb245 (\S+) MemFree:\d+ Dirty:(\d+) Writeback:(\d+)")
for rec in sys.argv[1:]:
    out = err = ""
    for line in open(f"{rec}/report.jsonl"):
        d = json.loads(line)
        if d.get("$report_type") == "TestReport" and d.get("when") == "setup":
            s = dict(d.get("sections", []))
            if "capture started" in s.get("Captured stderr setup", ""):
                out, err = s["Captured stdout setup"], s["Captured stderr setup"]; break
    t0 = datetime.fromisoformat(re.search(r"^(\S+) capture started", err, re.M).group(1))
    rows = {}
    for l in out.splitlines():
        m = HB.match(l)
        if m and datetime.fromisoformat(m.group(1).replace(",", ".")) >= t0:
            rows[float(m.group(2))] = (int(m.group(3)), int(m.group(4)))
    if rec.endswith("20261102T205017Z"):
        rows[601.22] = (4484, 11576)
    u = sorted(rows); best = (0, None); i = 0
    while i < len(u):
        d0 = rows[u[i]][0]; j = i
        while j + 1 < len(u) and abs(rows[u[j+1]][0] - d0) <= 100 and rows[u[j+1]][1] > 0: j += 1
        if u[j] - u[i] > best[0]: best = (u[j] - u[i], u[i])
        i = j + 1 if j > i else i + 1
    print(rec.split("/")[-1], f"longest flat-Dirty stretch {best[0]:.2f}s from uptime {best[1]}")
