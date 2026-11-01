#!/usr/bin/env python3
"""Per-run install progress over records: for each record, the [stats]
write-sector delta (mmc field 7) at each sample, measured from the first
[stats] sample, against seconds since 'capture started'. Prints, per run,
the total written, and the time at which the run passed a target delta
(argv[1], sectors). Read-only."""
import json, re, sys
from datetime import datetime

LINE = re.compile(r"^(\S+) \[(\w+)\] (.*)$")


def sections(rec):
    for line in open(f"{rec}/report.jsonl"):
        d = json.loads(line)
        if d.get("$report_type") != "TestReport" or d.get("when") != "setup":
            continue
        s = dict(d.get("sections", []))
        if "capture started" in s.get("Captured stderr setup", ""):
            return s.get("Captured stdout setup", ""), s["Captured stderr setup"]
    return None, None


target = int(sys.argv[1])
for rec in sys.argv[2:]:
    out, err = sections(rec)
    if out is None:
        continue
    start = None
    for l in err.splitlines():
        if l.endswith("capture started"):
            start = datetime.fromisoformat(l.split()[0])
    w0 = None
    t_at = None
    last = None
    for l in out.splitlines():
        m = LINE.match(l)
        if not m or m.group(2) != "stats" or "mmc=" not in l:
            continue
        f = l.split("mmc=")[1].split()
        ws = int(f[6])
        t = (datetime.fromisoformat(m.group(1)) - start).total_seconds()
        if w0 is None:
            w0 = ws
        d = ws - w0
        if t_at is None and d >= target:
            t_at = t
        last = (t, d)
    print(rec.split("/")[-1], f"total_written={last[1]} at_t={last[0]:.1f}",
          f"t_reach_target={t_at if t_at is None else round(t_at, 1)}")
