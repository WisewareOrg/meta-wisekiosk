#!/usr/bin/env python3
"""Max load1 and hb count in each record's install window (host [kernel]
hb245 lines printed after 'capture started'). Read-only."""
import json, re, sys
from datetime import datetime
for rec in sys.argv[1:]:
    out = err = ""
    for line in open(f"{rec}/report.jsonl"):
        d = json.loads(line)
        if d.get("$report_type") == "TestReport" and d.get("when") == "setup":
            s = dict(d.get("sections", []))
            if "capture started" in s.get("Captured stderr setup", ""):
                out, err = s["Captured stdout setup"], s["Captured stderr setup"]; break
    t0 = datetime.fromisoformat(re.search(r"^(\S+) capture started", err, re.M).group(1))
    loads = []
    for l in out.splitlines():
        m = re.match(r"^\S+ \[kernel\] (\d{4}-\S+) hb245 \S+ .*load=(\S+)", l)
        if m and datetime.fromisoformat(m.group(1).replace(",", ".")) >= t0:
            loads.append(float(m.group(2)))
    print(rec.split("/")[-1], "hb", len(loads), "max_load1", max(loads) if loads else None)
