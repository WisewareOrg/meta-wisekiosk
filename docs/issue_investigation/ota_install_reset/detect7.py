#!/usr/bin/env python3
"""Would the soft-lockup detector (watchdog_thresh=3) have fired before the
hardware-watchdog reset in reset 7? kernel/watchdog.c (6.12.93): hrtimer every
sample_period = 2*thresh/5 = 1.2 s queues the touch (UP: schedule_work); the
touch stores get_timestamp() = sched_clock >> 30 (u = 1.073741824 s units);
a tick reports when floor(now/u) > floor(touch/u) + 2*thresh. Monte Carlo
over stop time S, hrtimer phase, reset time R. Read-only arithmetic."""
import random, math
u = 2**30 / 1e9; per = 1.2; th = 6
def detect(S, phi):
    n = math.floor((S - phi) / per); touch = phi + n * per     # last tick <= S, touch at tick
    t = touch
    while True:
        t += per
        if math.floor(t / u) > math.floor(touch / u) + th:
            return t
def run(Slo, Shi, Rlo, Rhi, dump, N=200000, thr=th, prd=per):
    global th, per
    th, per = thr, prd
    ok = 0; lat = []
    for _ in range(N):
        S = random.uniform(Slo, Shi); phi = random.uniform(0, per); R = random.uniform(Rlo, Rhi)
        d = detect(S, phi); lat.append(d - S)
        ok += d + dump < R
    lat.sort()
    return ok / N, lat[0], lat[len(lat)//2], lat[-1]
random.seed(7)
for (Slo, Shi, Rlo, Rhi, lab) in [(511.40, 512.60, 519.06, 519.12, "k=1.00"), (511.40, 512.60, 519.06, 519.84, "k in [1,1.08]")]:
    for dump in (0.0, 0.5):
        p, mn, md, mx = run(Slo, Shi, Rlo, Rhi, dump)
        print(f"thresh=3 {lab:14s} dump={dump:.1f}s  P(dmesg record before reset)={p:.2f}  detect latency after stop min {mn:.2f} med {md:.2f} max {mx:.2f}  stop->reset {Rlo-Shi:.2f}..{Rhi-Slo:.2f}")
# same detector, reset 5's geometry (stop ~0.5 s after the last pet, reset 14 s after it)
p, mn, md, mx = run(435.8, 436.5, 449.80, 450.14, 0.5)
print(f"thresh=3 reset-5 geometry dump=0.5  P={p:.2f}")
# worst-case geometry: stop just before a due pet (pet interval up to 7.7 s) -> 6.3 s to reset
for thr, prd in ((6, 1.2), (4, 0.8), (2, 0.4)):
    p, mn, md, mx = run(0.0, 0.0001, 6.3, 6.3001, 0.5, thr=thr, prd=prd)
    print(f"softlockup thresh {thr}s (watchdog_thresh={thr//2}) worst geometry (6.3 s stop->reset, dump 0.5): P={p:.2f} latency max {mx:.2f}")
