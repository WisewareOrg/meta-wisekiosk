#!/usr/bin/env python3
"""Hung-task episodes (same task, reports <=2.2 s apart) in healthy records:
how many reached >=N s and how many of those were reported again 2 s later.
Base rate for 'a 33 s mmc_rescan episode ends before its next report'. Read-only."""
import json, re, sys
from datetime import datetime
N = 33; eps = []
for rec in sys.argv[1:]:
    out = err = ""
    for line in open(f"{rec}/report.jsonl"):
        d = json.loads(line)
        if d.get("$report_type") == "TestReport" and d.get("when") == "setup":
            s = dict(d.get("sections", []))
            if "capture started" in s.get("Captured stderr setup", ""):
                out, err = s["Captured stdout setup"], s["Captured stderr setup"]; break
    seen = {}
    for l in out.splitlines():
        m = re.match(r"^\S+ \[kernel\] (\d{4}-\S+) INFO: task (\S+) blocked for more than (\d+) seconds", l)
        if m: seen[m.group(1)] = (datetime.fromisoformat(m.group(1).replace(",", ".")), m.group(2), int(m.group(3)))
    cur = {}
    for b, t, n in sorted(seen.values()):
        if t in cur and (b - cur[t][-1][0]).total_seconds() <= 2.3: cur[t].append((b, n))
        else:
            if t in cur: eps.append(max(x[1] for x in cur[t]))
            cur[t] = [(b, n)]
    eps += [max(x[1] for x in v) for v in cur.values()]
reach = [e for e in eps if e >= N]; cont = [e for e in reach if e >= N + 2]
print(f"episodes {len(eps)}; reached >={N}s: {len(reach)}; of those reported again (>= {N+2}s): {len(cont)}; ended: {len(reach)-len(cont)}")
