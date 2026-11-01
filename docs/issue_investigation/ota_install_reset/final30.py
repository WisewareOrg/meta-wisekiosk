#!/usr/bin/env python3
"""Final N heartbeats of a record, pstore and host [kernel] stream joined on
the uptime field. Prints host recv, board stamp, printk, uptime, wdt, p1,
wchan, majflt, load1, Dirty, WB, and mmc deltas (reads completed, read
sectors, writes completed, write sectors) since the previous heartbeat.
Read-only."""
import re, sys
rec, n = sys.argv[1], int(sys.argv[2])
W = "/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/reset5"
HB = re.compile(r"hb245 (\S+) MemFree:(\d+) Dirty:(\d+) Writeback:(\d+) load=(\S+) \S+ \S+ mmc=((?:\d+ ){16}\d+) uv=(\d) freq=(\d+) wdt=(\d+) p1=(\S+) p1wchan=(\S*) p1majflt=(\d+)")
ps = {}
for l in open(f"{rec}/pstore/console-ramoops-0"):
    m = re.match(r"\[\s*([\d.]+)\] (hb245.*)", l)
    if m:
        h = HB.search(m.group(2))
        if h:
            ps[h.group(1)] = (float(m.group(1)), h)
host = {}
for l in open(f"{W}/stdout.redacted"):
    m = re.match(r"^(\S+) \[kernel\] (\S+) (hb245.*)", l)
    if m:
        h = HB.search(m.group(3))
        host[h.group(1)] = (m.group(1)[11:26], m.group(2)[11:26])
keys = sorted(ps, key=float)
print("pstore hb", len(ps), "host kernel hb", len(host), "pstore-only", sorted(set(ps)-set(host), key=float)[-5:], "host-only", sorted(set(host)-set(ps), key=float)[-5:])
print("| host recv | board | printk | uptime | wdt | p1 | p1wchan | majflt | load1 | Dirty | WB | dR | dRsec | dW | dWsec |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
prev = None
for k in keys[-(n+1):]:
    pk, h = ps[k]
    mmc = list(map(int, h.group(6).split()))
    if prev is not None:
        d = [mmc[i]-prev[i] for i in (0, 2, 4, 6)]
        hr, bd = host.get(k, ("-", "-"))
        print(f"| {hr} | {bd} | {pk:.3f} | {k} | {h.group(9)} | {h.group(10)} | {h.group(11)} | {h.group(12)} | {h.group(5)} | {h.group(3)} | {h.group(4)} | {d[0]} | {d[1]} | {d[2]} | {d[3]} |")
    prev = mmc
