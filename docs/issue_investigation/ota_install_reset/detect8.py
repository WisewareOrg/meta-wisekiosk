#!/usr/bin/env python3
"""Would the soft-lockup detector (watchdog_thresh=1) have fired before the
hardware-watchdog reset in reset 8? kernel/watchdog.c (6.12.93): hrtimer every
sample_period = 2*thresh/5 = 0.4 s queues the touch (UP: schedule_work); the
touch stores get_timestamp() = running_clock >> 30 (u = 1.073741824 s units);
a tick reports when now > period_ts + 2*thresh (time_after). Monte Carlo over
stop time S, hrtimer phase, reset time R. Same model as reset7/detect7.py.
Read-only arithmetic."""
import random, math
u = 2**30 / 1e9
def detect(S, phi, per, th):
    n = math.floor((S - phi) / per); touch = phi + n * per
    t = touch
    while True:
        t += per
        if math.floor(t / u) > math.floor(touch / u) + th:
            return t
def run(Slo, Shi, Rlo, Rhi, dump, per=0.4, th=2, N=200000):
    ok = 0; lat = []
    for _ in range(N):
        S = random.uniform(Slo, Shi); phi = random.uniform(0, per); R = random.uniform(Rlo, Rhi)
        d = detect(S, phi, per, th); lat.append(d - S); ok += d + dump < R
    lat.sort()
    return ok / N, lat[0], lat[len(lat)//2], lat[-1]
random.seed(8)
cases = [((601.37, 601.86), "S by delivery bound"), ((601.37, 602.35), "S by next-hb bound")]
Rs = [((613.79, 613.90), "R tail~0"), ((613.79, 614.90), "R tail<=1s")]
for (Slo, Shi), sl in cases:
    for (Rlo, Rhi), rl in Rs:
        for dump in (0.0, 0.5, 2.0, 5.0):
            p, mn, md, mx = run(Slo, Shi, Rlo, Rhi, dump)
            print(f"thresh=1 {sl:20s} {rl:10s} dump={dump:.1f}s  P(record before reset)={p:.3f}  latency after stop min {mn:.2f} med {md:.2f} max {mx:.2f}  stop->reset {Rlo-Shi:.2f}..{Rhi-Slo:.2f}  slack(min window - max latency) {Rlo-Shi-mx:.2f}")
# Same stop under reset 7's thresh=3 detector, for contrast
p, mn, md, mx = run(601.37, 602.35, 613.79, 613.90, 0.5, per=1.2, th=6)
print(f"contrast: thresh=3 on this geometry dump=0.5  P={p:.3f} latency max {mx:.2f}")
# thresh=1 on reset 7's geometry (stop just before a due pet)
p, mn, md, mx = run(511.40, 512.60, 519.06, 519.12, 0.5)
print(f"contrast: thresh=1 on reset-7 geometry dump=0.5  P={p:.3f}")
