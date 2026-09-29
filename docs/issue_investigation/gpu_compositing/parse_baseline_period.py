"""parse_baseline.py with the beat period as a parameter (W10, appliance Runs 49+).

    python3 parse_baseline_period.py [--period P | --period auto] <capture> [<capture> ...]

parse_baseline.py hardcodes 40 s twice -- the steady cutoff (t >= 40 s) and the on-beat fold
(t mod 40 within +/-3 s) -- because Run 41's measured beat was 40 s. A capture whose beat is not 40 s
is mis-bucketed by it. This is the same read with P in place of 40 in the fold ONLY; the steady cutoff
stays at 40 s, as recorded, so startup is excluded exactly as Run 41's read excluded it.

  --period 40    (default) output is line-for-line parse_baseline.py's; proved on baseline-588s-raw.txt
  --period auto  P = the median gap between consecutive steady (t >= 40 s) arrivals >= 250 ms after
                 clustering arrivals within 2 s (parse_rotation.py's CLUSTER_S), rounded to 0.1 s;
                 printed with the gaps it came from, so the choice can be checked by eye. The fold is
                 then anchored at the beat's own phase: the median of t mod P over the longest chain of
                 arrivals whose consecutive gaps are within +/-3 s of P. (parse_baseline.py's fold is
                 anchored at t mod 40 = 0, which Run 41 happened to sit on at +0.5 s; a beat at another
                 phase would read as all off-beat.) With a fixed --period the anchor stays 0, as recorded.
"""
import re, statistics, sys

STEADY_S = 40.0      # parse_baseline.py's startup cutoff, unchanged
TOL = 3.0            # parse_baseline.py's on-beat window
CLUSTER_S = 2.0


def parse(path):
    txt = open(path).read()
    m = re.search(r'BL\|(\d+)\|f(\d+)\|big(\d+)\|av(\d+)\|mx(\d+)\|H([\d.]+)\|S\[([^\]]*)\]', txt)
    if not m:
        sys.exit(f'{path}: no p30_baseline.js payload (BL|el|f|big|av|mx|H|S[...]) -- for p31_rotcheck.js use parse_rotation.py')
    el, fr, big, av, mx = (int(m.group(i)) for i in range(1, 6))
    hist = [int(x) for x in m.group(6).split('.')]
    stalls = []
    for e in m.group(7).split(','):
        t, d = e.split(':')
        stalls.append((float(t), int(d)))
    return dict(path=path, el=el, fr=fr, big=big, av=av, mx=mx, hist=hist, stalls=stalls)


def auto_period(steady):
    ev = []
    for t, d in sorted(steady):
        if d >= 250 and (not ev or t - ev[-1] > CLUSTER_S):
            ev.append(t)
    gaps = [round(ev[i + 1] - ev[i], 1) for i in range(len(ev) - 1)]
    return (round(statistics.median(gaps), 1) if gaps else None), gaps


def auto_phase(steady, P):
    ev = []
    for t, d in sorted(steady):
        if d >= 250 and (not ev or t - ev[-1] > CLUSTER_S):
            ev.append(t)
    best, cur = [], ev[:1]
    for a, b in zip(ev, ev[1:]):
        if abs((b - a) - P) <= TOL:
            cur.append(b)
        else:
            best, cur = max(best, cur, key=len), [b]
    best = max(best, cur, key=len)
    return round(statistics.median(t % P for t in best), 1), best


def report(p, period):
    r = parse(p)
    print('=' * 72)
    print(r['path'])
    print(f"  window {r['el']}s  frames {r['fr']}  big {r['big']}  mean {r['av']}ms  max {r['mx']}ms")
    print(f"  hist(<50,50-100,100-250,250-500,500-1k,1k-2k,>=2k) {r['hist']}  sum={sum(r['hist'])}")
    print(f"  hist>250 = {sum(r['hist'][3:])}   recorded stalls in S[] = {len(r['stalls'])}")
    print(f"  rate = {r['big']}/{r['el']} = {r['big']/r['el']:.4f}/s")
    st = r['stalls']
    steady = [s for s in st if s[0] >= STEADY_S]
    print(f"  stalls listed: {[f'{t}:{d}' for t,d in st]}")
    print(f"  --- steady (t>=40s): n={len(steady)}")
    print(f"      durations {[d for t,d in steady]}")
    if steady:
        ds = [d for t, d in steady]
        print(f"      duration min/max {min(ds)}/{max(ds)}  mean {sum(ds)/len(ds):.0f}")
    if period == 'auto':
        P, gaps = auto_period(steady)
        print(f"  --- period auto: clustered steady gaps {gaps} -> median {P}s")
        if P is None:
            print("  --- no period: fewer than two steady arrivals")
            return
        ph, chain = auto_phase(steady, P)
        print(f"  --- phase auto: chain {chain} -> t mod {P:g} = {ph}s")
    else:
        P = float(period)
        ph = 0.0
    on = [s for s in steady if abs(((s[0] - ph) % P)) < TOL or abs(((s[0] - ph) % P) - P) < TOL]
    lab = f"t mod {P:g}" if ph == 0.0 else f"(t - {ph:g}) mod {P:g}"
    print(f"  --- on-beat ({lab} within +/-3s), n={len(on)}: {[f'{t}:{d}' for t,d in on]}")
    if len(on) > 1:
        iv = [round(on[i+1][0]-on[i][0], 1) for i in range(len(on)-1)]
        print(f"      intervals {iv}")
    off = [s for s in steady if s not in on]
    print(f"  --- off-beat, n={len(off)}: {[f'{t}:{d}' for t,d in off]}")


if __name__ == '__main__':
    args = sys.argv[1:]
    period = '40'
    if args[:1] == ['--period']:
        period, args = args[1], args[2:]
    for p in args:
        report(p, period)
