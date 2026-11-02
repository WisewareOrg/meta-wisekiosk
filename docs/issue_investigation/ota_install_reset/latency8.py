#!/usr/bin/env python3
"""Live [kernel]-stream latency (host recv - printk board stamp) for lines
printed after the install started, to bound when delivery stopped. Read-only."""
import re, sys
from datetime import datetime
S = "/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/reset8"
lat = []; hb = []
for l in open(f"{S}/stdout.redacted"):
    m = re.match(r"^(\S+) \[kernel\] (\d{4}-\S+) (.*)", l)
    if not m: continue
    h = datetime.fromisoformat(m.group(1)); b = datetime.fromisoformat(m.group(2).replace(",", "."))
    if b.strftime("%H:%M:%S") < "15:52:10": continue
    d = (h - b).total_seconds(); lat.append(d)
    if m.group(3).startswith("hb245"): hb.append(d)
for name, x in (("all live lines", lat), ("live hb245 lines", hb)):
    x = sorted(x); n = len(x)
    print(f"{name}: n={n} min {x[0]:.3f} p50 {x[n//2]:.3f} p90 {x[int(n*.9)]:.3f} p99 {x[int(n*.99)]:.3f} max {x[-1]:.3f}  >=0.4s: {sum(v>=0.4 for v in x)}")
