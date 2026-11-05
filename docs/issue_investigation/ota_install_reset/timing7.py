#!/usr/bin/env python3
"""Reset-7 clocks and watchdog timing test (method of reset5/timing.py).
Inputs: the record's setup stdout (host [kernel] stream), pstore console,
remote-read.out (20 host-stamped /proc/uptime samples). Read-only."""
import re
from datetime import datetime, timedelta, timezone
S = "/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/reset7"
REC = "/home/tjwise/meta-wisekiosk/records/20261102T074924Z"
EST = timezone(timedelta(hours=-5))
offs = []; last = None
for l in open(f"{S}/stdout-test_buildinfo_names_commit.txt"):
    m = re.match(r"^(\S+) \[kernel\] (\S+) hb245 (\S+)", l)
    if m:
        h = datetime.fromisoformat(m.group(1)); b = datetime.fromisoformat(m.group(2).replace(",", "."))
        offs.append((h - b).total_seconds()); last = (h, b, float(m.group(3)))
offs.sort(); OFF = offs[0]
print(f"[kernel] lines {len(offs)}  host-board min {OFF:.4f} median {offs[len(offs)//2]:.4f}")
rows = []
for l in open(f"{REC}/pstore/console-ramoops-0"):
    m = re.match(r"\[\s*([\d.]+)\] hb245 (\S+) .* wdt=(\d+) ", l)
    if m:
        rows.append((float(m.group(2)), float(m.group(1)), int(m.group(3))))
u_last, pk0, w_last = rows[-1]
h_last, b0, _ = last
print(f"pstore hb {len(rows)}  last printk {pk0} uptime-field {u_last} wdt {w_last}  board {b0.time()} host recv {h_last.time()}")
pz = b0 - timedelta(seconds=pk0)
print("boot -1 printk zero (board)", pz.time())
js = datetime(2026, 11, 2, 2, 44, 33, 679934, tzinfo=EST)
print(f"F (boot -2 Journal stopped -> boot -1 printk zero) = {(pz - js).total_seconds():.3f} s")
ks = []
for l in open(f"{S}/remote-read.out"):
    p = l.split()
    if len(p) == 3:
        try: ks.append(float(p[0]) - float(p[1]))
        except ValueError: pass
ks.sort()
K = datetime.fromtimestamp(ks[0], EST)
print(f"uptime samples {len(ks)} spread {ks[-1]-ks[0]:.3f}  K (host) {K.time()}")
dh = datetime(2026, 11, 2, 2, 53, 27, 554542, tzinfo=EST) + timedelta(seconds=OFF)
print(f"cross-check dmesg iso head + OFF = {dh.time()}  delta {(dh-K).total_seconds():+.3f}")
def host(t): return (b0 + timedelta(seconds=t - pk0 + OFF)).strftime("%H:%M:%S.%f")[:-4]
def pk(dt): return pk0 + (dt - b0).total_seconds() - OFF
print(f"last hb -> K: {(K - (b0 + timedelta(seconds=OFF))).total_seconds():.2f} s")
obs_lo, obs_hi = K - timedelta(seconds=7.43), K - timedelta(seconds=7.32 - 1.0)
olo, ohi = pk(obs_lo), pk(obs_hi)
print(f"observed reset (K - B, B<=F in [7.32,7.43], tail<=1.0) host {obs_lo.time()}..{obs_hi.time()}  printk {olo:.2f}..{ohi:.2f}")
for k in (1.00, 1.02, 1.05, 1.08):
    pw = None; lo = hi = None
    for u, p, w in rows:
        l, h = u - k * (14 - w), p - k * (13 - w)
        if pw is not None and w <= pw: lo, hi = max(lo, l), min(hi, h)
        else: lo, hi = l, h
        pw = w
    A = (lo + 14 * k, hi + 14 * k)
    Qlo, Qhi = max(u_last, lo + 3.5 * k), hi + 7 * k + 0.5
    B = (Qlo + 14 * k, Qhi + 14 * k)
    def miss(a, b):
        if b < olo: return olo - b
        if a > ohi: return -(a - ohi)
        return 0.0
    print(f"k={k:.2f} P=[{lo:.2f},{hi:.2f}]{' EMPTY' if hi < lo else ''} A(no further pet): reset {A[0]:.2f}..{A[1]:.2f} host {host(A[0])}..{host(A[1])} miss {miss(*A):+.2f}s"
          f" | B(one more pet Q=[{Qlo:.2f},{Qhi:.2f}]): reset {B[0]:.2f}..{B[1]:.2f} miss {miss(*B):+.2f}s  Q needed >= {olo-14*k:.2f}")
