#!/usr/bin/env python3
"""Clock arithmetic for reset 5. Read-only; inputs are the record's stdout
section (stdout.redacted) and remote-read.out."""
import re
from datetime import datetime, timezone, timedelta
W = "/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/reset5"
EST = timezone(timedelta(hours=-5))
# host - board offset over [kernel] lines
offs = []
last = None
for l in open(f"{W}/stdout.redacted"):
    m = re.match(r"^(\S+) \[kernel\] (\S+) hb245 (\S+)", l)
    if not m:
        continue
    h = datetime.fromisoformat(m.group(1))
    b = datetime.fromisoformat(m.group(2).replace(",", "."))
    offs.append(((h - b).total_seconds(), m.group(3)))
    last = (h, b, float(m.group(3)))
offs.sort()
print("kernel lines", len(offs), "min host-board", offs[0], "median", offs[len(offs)//2][0])
# kernel start in host clock
ks = []
for l in open(f"{W}/remote-read.out"):
    p = l.split()
    if len(p) == 3:
        try:
            ks.append(float(p[0]) - float(p[1]))
        except ValueError:
            pass
ks.sort()
k = ks[0]
print("uptime samples", len(ks), "min host_recv-uptime", round(k, 4), "spread", round(ks[-1]-k, 4))
kdt = datetime.fromtimestamp(k, EST)
print("kernel start host", kdt.isoformat())
h_last, b_last, u_last = last
print("last hb host", h_last.isoformat(), "board", b_last.isoformat(), "uptime field", u_last)
off = offs[0][0]
print("last hb board->host", (b_last + timedelta(seconds=off)).isoformat())
gap_host = (kdt - h_last).total_seconds()
gap_board = (kdt - (b_last + timedelta(seconds=off))).total_seconds()
print("gap last-hb(host recv)->kernel start", round(gap_host, 3), " gap last-hb(board stamp+off)->kernel start", round(gap_board, 3))
