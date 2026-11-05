#!/usr/bin/env python3
"""Bound PID1's watchdog pet times from hb245 wdt readings. timeleft
truncates (bcm2835_wdt.c), so a reading w at read time t means the last pet
P satisfies t-14+w <= P < t-13+w. The read time lies between the uptime
field u and the printk time; printk is reconstructed per run as
u + (board_iso - u) - min over the run of (board_iso - u). Consecutive
samples with non-increasing wdt share a pet; their windows are intersected.
Prints per run the pet-interval bounds (lo = earliest possible next pet -
latest possible previous pet, hi = the reverse). Read-only."""
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
allint = []
for rec in sys.argv[1:]:
    rows = []
    for l in sec(rec).splitlines():
        m = HB.match(l)
        if m:
            b = datetime.fromisoformat(m.group(1).replace(",", ".")).timestamp()
            rows.append((float(m.group(2)), b, int(m.group(3))))
    if not rows:
        continue
    base = min(b - u for u, b, w in rows)
    pets = []  # [lo, hi]
    pw = None
    for u, b, w in rows:
        pk = u + (b - u) - base
        lo, hi = u - 14 + w, pk - 13 + w
        if pw is not None and w <= pw and pets:
            pets[-1] = [max(pets[-1][0], lo), min(pets[-1][1], hi)]
        else:
            pets.append([lo, hi])
        pw = w
    iv = []
    for a, c in zip(pets, pets[1:]):
        iv.append((c[0] - a[1], c[1] - a[0]))
    allint += iv
    if rec.endswith("090332Z") or len(sys.argv) == 2:
        for p in pets[-4:]:
            print(rec[-16:], "pet window %.2f..%.2f" % tuple(p))
        print(rec[-16:], "last intervals", ["%.2f..%.2f" % x for x in iv[-4:]])
bad = [x for x in allint if x[1] < x[0]]
print("intervals", len(allint), "inconsistent", len(bad))
print("max lower bound on any pet interval: %.2f s" % max(x[0] for x in allint))
print("min upper bound on any pet interval: %.2f s" % min(x[1] for x in allint))
print("intervals whose lower bound > 7.0:", sum(1 for x in allint if x[0] > 7.0), " > 7.2:", sum(1 for x in allint if x[0] > 7.2), " > 7.5:", sum(1 for x in allint if x[0] > 7.5))
print("intervals whose upper bound < 7.0:", sum(1 for x in allint if x[1] < 7.0), " < 6.0:", sum(1 for x in allint if x[1] < 6.0))
