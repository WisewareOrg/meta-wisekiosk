#!/usr/bin/env python3
"""Numbers this investigation records from its radio-watch captures.

    analyze.py watch <capture>               rx bitrate counts, tx failed range, times below 19.5 MBit/s
    analyze.py pair <bench> <prod> [MBit]    each bench sample paired with the nearest prod sample within
                                             5 s (host clock); rows where either reads <= MBit, counts of
                                             lows on each side and on both, the largest |dt| used, and
                                             the samples left unpaired on each side
"""
import re
import sys
from collections import Counter

WATCH = re.compile(
    r"^(?P<t>\d\d:\d\d:\d\d) \S+ \|.*?tx failed: (?P<fail>\d+).*?"
    r"tx bitrate: (?P<tx>[\d.]+).*?rx bitrate: (?P<rx>[\d.]+)"
)
PAIR_WITHIN_S = 5


def watch_rows(path: str) -> list[dict]:
    """Parse one radio-watch capture into its samples, in order."""
    with open(path, errors="replace") as capture:
        rows = [m.groupdict() for m in map(WATCH.search, capture) if m]
    for row in rows:
        h, m, s = map(int, row["t"].split(":"))
        row["s"] = h * 3600 + m * 60 + s
    return rows


def watch(path: str) -> None:
    rows = watch_rows(path)
    print(f"samples {len(rows)}")
    for rate, n in sorted(Counter(r["rx"] for r in rows).items(), key=lambda kv: -float(kv[0])):
        print(f"rx {rate:>5} MBit/s: {n}")
    fails = [int(r["fail"]) for r in rows]
    print(f"tx failed {min(fails)} -> {max(fails)}")
    print("rx below 19.5 at:", " ".join(r["t"] for r in rows if float(r["rx"]) < 19.5) or "none")


def pair(bench_path: str, prod_path: str, low: float) -> None:
    bench, prod = watch_rows(bench_path), watch_rows(prod_path)
    pairs, used = [], set()
    for b in bench:
        near = min(
            ((abs(p["s"] - b["s"]), i) for i, p in enumerate(prod) if i not in used),
            default=None,
        )
        if near is not None and near[0] <= PAIR_WITHIN_S:
            used.add(near[1])
            pairs.append((b, prod[near[1]], near[0]))
    lows = Counter()
    for b, p, _ in pairs:
        b_low, p_low = float(b["rx"]) <= low, float(p["rx"]) <= low
        lows["bench"] += b_low
        lows["prod"] += p_low
        lows["both"] += b_low and p_low
        if b_low or p_low:
            print(f"{b['t']} bench rx {b['rx']:>5} fail {b['fail']:>4} | "
                  f"{p['t']} prod rx {p['rx']:>5} fail {p['fail']:>4}")
    print(f"pairs {len(pairs)}; largest |dt| {max((d for *_, d in pairs), default=0)} s; "
          f"unpaired bench {len(bench) - len(pairs)}, prod {len(prod) - len(used)}")
    print(f"pairs at or below {low} MBit/s: bench {lows['bench']}, prod {lows['prod']}, both {lows['both']}")
    for name, rows in (("bench", bench), ("prod", prod)):
        print(f"{name} tx failed {rows[0]['fail']} -> {rows[-1]['fail']}" if rows else f"{name}: no samples")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "watch":
        watch(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "pair":
        pair(sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 6.5)
    else:
        sys.exit(__doc__)
