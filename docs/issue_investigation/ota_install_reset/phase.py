#!/usr/bin/env python3
"""For each record: over [stats] samples whose write-sector delta (from the
first sample) lies in [lo, hi], the reads completed, max Writeback (kB),
max load1 and the longest run of consecutive samples with zero new reads.
Read-only."""
import json, re, sys
lo, hi = int(sys.argv[1]), int(sys.argv[2])
def sec(rec):
    for line in open(f"{rec}/report.jsonl"):
        d = json.loads(line)
        if d.get("$report_type") == "TestReport" and d.get("when") == "setup":
            s = dict(d.get("sections", []))
            if "capture started" in s.get("Captured stderr setup", ""):
                return s.get("Captured stdout setup", "")
for rec in sys.argv[3:]:
    w0 = None; prev = None; reads = 0; wb = 0; ld = 0; zr = 0; zrmax = 0; n = 0
    for l in sec(rec).splitlines():
        if " [stats] " not in l or "mmc=" not in l:
            continue
        f = list(map(int, l.split("mmc=")[1].split()[:7]))
        WB = int(re.search(r"Writeback:(\d+)", l).group(1)); L = float(re.search(r"load=(\S+)", l).group(1))
        if w0 is None: w0 = f[6]
        d = f[6] - w0
        if lo <= d <= hi and prev is not None:
            n += 1; r = f[0] - prev[0]; reads += r; wb = max(wb, WB); ld = max(ld, L)
            zr = zr + 1 if r == 0 else 0; zrmax = max(zrmax, zr)
        prev = f
    print(rec.split("/")[-1], f"n={n} reads={reads} maxWB={wb} maxload={ld} longest_zero_read_run={zrmax}")
