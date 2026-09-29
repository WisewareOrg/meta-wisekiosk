"""Phase of the steady big frames against the shipped mechanism's 8 s cycle (Run 26b's read).

    python3 parse_phase.py <capture> [<capture> ...]

Run 26b's phase read was an inline command in the session that ran it; this is that read as a
file (R2). It takes the big-frame list from an MP payload (`|B<t:dt,...>`, last 14) or a BL
payload (`|S[<t:dt,...>]`), drops startup (t < 6 s, the README's "five arrive before t=6 s"),
and prints each arrival's t mod 8 s and how many fall in the scroll-start window [1.5, 3.0] s
(the inline read's window). An MP list with BT above its 14 entries is truncated and is
reported as such: a phase read from it covers the last 14 arrivals, not the window.
"""
import re
import sys

PERIOD = 8.0
STARTUP_S = 6.0
WIN = (1.5, 3.0)
MP_CAP = 14


def big_frames(txt):
    m = re.search(r'MP\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|H([\d.]+)\|B([^"\n]*)', txt)
    if m:
        pairs = re.findall(r'([\d.]+):(\d+)', m.group(7))
        return 'MP', int(m.group(1)), int(m.group(5)), [(float(t), int(d)) for t, d in pairs]
    m = re.search(r'BL\|(\d+)\|f(\d+)\|big(\d+)\|av(\d+)\|mx(\d+)\|H([\d.]+)\|S\[([^\]]*)\]', txt)
    if m:
        pairs = re.findall(r'([\d.]+):(\d+)', m.group(7))
        return 'BL', int(m.group(1)), int(m.group(3)), [(float(t), int(d)) for t, d in pairs]
    return None


def main(paths):
    rc = 0
    for p in paths:
        print('=' * 72)
        print(p)
        got = big_frames(open(p).read())
        if not got:
            print('  no MP or BL payload')
            rc = 1
            continue
        kind, el, count, pairs = got
        listed = len(pairs)
        truncated = kind == 'MP' and count > listed
        print(f'  {kind} payload, window {el}s, big frames counted {count}, listed {listed}'
              + ('  ** TRUNCATED: phase covers the last listed arrivals only **' if truncated else ''))
        steady = [(t, d) for t, d in pairs if t >= STARTUP_S]
        mods = [round(t % PERIOD, 1) for t, _ in steady]
        inwin = [x for x in mods if WIN[0] <= x <= WIN[1]]
        print(f'  startup (t < {STARTUP_S:g}s): {listed - len(steady)}   steady: {len(steady)}')
        print(f'  t mod {PERIOD:g}s: {mods}')
        if mods:
            print(f'  {len(inwin)} of {len(mods)} in [{WIN[0]}, {WIN[1]}] s'
                  + (f'; in-window range {min(inwin)}-{max(inwin)} s' if inwin else ''))
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
