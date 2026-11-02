#!/usr/bin/env python3
"""Per record: hung-task reports in the install window (host [kernel] stream,
de-duplicated by printk board stamp), the max 'blocked for more than N'
and the report spacing. Read-only."""
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
    seen = {}
    for l in out.splitlines():
        m = re.match(r"^\S+ \[kernel\] (\d{4}-\S+) INFO: task (\S+) blocked for more than (\d+) seconds", l)
        if m:
            b = datetime.fromisoformat(m.group(1).replace(",", "."))
            if b >= t0: seen[m.group(1)] = (b, m.group(2), int(m.group(3)))
    v = sorted(seen.values())
    sp = [(v[i+1][0]-v[i][0]).total_seconds() for i in range(len(v)-1)]
    tasks = sorted({t for _, t, _ in v})
    print(rec.split("/")[-1], "reports", len(v), "max_blocked", max((n for *_, n in v), default=0),
          "tasks", tasks, "spacing", f"{min(sp):.2f}-{max(sp):.2f}" if sp else "-")
