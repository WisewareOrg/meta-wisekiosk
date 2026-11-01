#!/usr/bin/env python3
"""Reset-5 timing test. Read window per heartbeat = [uptime field, printk]
(pstore). Watchdog scale k (hw s -> uptime s). Last pet P from the final
pet group; scenario A: no pet after P, reset at P + 14k; scenario B: one
more pet Q in [last read lower bound, P + 7k + 0.5] (0.5 s scheduling
allowance beyond the observed 7.21 s max-lower-bound interval), reset at
Q + 14k. Times converted printk -> host via the last heartbeat's printk
(435.199029) <-> board 04:06:30.118226 and host - board = +0.042 (latency
floor included). Observed reset = kernel start (host 04:06:52.195) - B,
B in [7.32 - 1.0 s unmeasured tail, 7.43] (B <= F). Read-only."""
import re
from datetime import datetime, timedelta, timezone
EST = timezone(timedelta(hours=-5))
rows = []
for l in open("/home/tjwise/meta-wisekiosk/records/20261101T090332Z/pstore/console-ramoops-0"):
    m = re.match(r"\[\s*([\d.]+)\] hb245 (\S+) .* wdt=(\d+) ", l)
    if m:
        rows.append((float(m.group(2)), float(m.group(1)), int(m.group(3))))
pk0 = 435.199029
b0 = datetime(2026, 11, 1, 4, 6, 30, 118226, tzinfo=EST)
OFF = 0.042
def host(t):
    return (b0 + timedelta(seconds=t - pk0 + OFF)).strftime("%H:%M:%S.%f")[:-4]
K = datetime(2026, 11, 1, 4, 6, 52, 195037, tzinfo=EST)
obs_lo, obs_hi = K - timedelta(seconds=7.43), K - timedelta(seconds=7.32 - 1.0)
print("observed reset (host)", obs_lo.strftime("%H:%M:%S.%f")[:-4], "..", obs_hi.strftime("%H:%M:%S.%f")[:-4])
def obs_printk(dt):
    return pk0 + (dt - b0).total_seconds() - OFF
olo, ohi = obs_printk(obs_lo), obs_printk(obs_hi)
print("observed reset (printk) %.2f .. %.2f" % (olo, ohi))
for k in (1.00, 1.02, 1.05, 1.08):
    pw = None; lo = hi = None
    for u, pk, w in rows:
        l, h = u - k * (14 - w), pk - k * (13 - w)
        if pw is not None and w <= pw:
            lo, hi = max(lo, l), min(hi, h)
        else:
            lo, hi = l, h
        pw = w
    u_last = rows[-1][0]
    A = (lo + 14 * k, hi + 14 * k)
    Qlo, Qhi = max(u_last, lo + 3.5 * k), hi + 7 * k + 0.5
    B = (Qlo + 14 * k, Qhi + 14 * k)
    def miss(a, b):
        if b < olo: return olo - b
        if a > ohi: return -(a - ohi)
        return 0.0
    print(f"k={k:.2f} P=[{lo:.2f},{hi:.2f}]{' EMPTY' if hi < lo else ''}  A: reset {A[0]:.2f}..{A[1]:.2f} host {host(A[0])}..{host(A[1])} miss {miss(*A):+.2f}s"
          f" | B: Q=[{Qlo:.2f},{Qhi:.2f}] reset {B[0]:.2f}..{B[1]:.2f} host {host(B[0])}..{host(B[1])} miss {miss(*B):+.2f}s")
    # B with zero scheduling allowance (pet exactly at <= P + 7k)
    Bz = (Qlo + 14 * k, hi + 7 * k + 14 * k)
    print(f"        B no-slack: reset {Bz[0]:.2f}..{Bz[1]:.2f} host {host(Bz[0])}..{host(Bz[1])} miss {miss(*Bz):+.2f}s")
