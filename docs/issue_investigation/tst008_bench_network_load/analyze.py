#!/usr/bin/env python3
"""Numbers this investigation records from its captures.

    analyze.py soak <capture>               hourly median load1 per day (samples at >= 900 s uptime)
    analyze.py watch <capture>              rx bitrate counts, tx failed range, low-rate sample times
    analyze.py pair <bench> <prod> [MBit]   samples aligned by host clock: both boards' rx bitrate
                                            and tx failed per 10 s, rows where either reads <= MBit
"""
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

EST = timezone(timedelta(hours=-5))
WATCH = re.compile(
    r"^(?P<t>\d\d:\d\d:\d\d) \S+ \|.*?tx failed: (?P<fail>\d+).*?"
    r"tx bitrate: (?P<tx>[\d.]+).*?rx bitrate: (?P<rx>[\d.]+)"
)


def soak(path: str) -> None:
    hours = defaultdict(list)
    for line in open(path, errors="replace"):
        if not line.startswith("ts="):
            continue
        kv = dict(f.split("=", 1) for f in line.split() if "=" in f)
        if int(kv["up"]) < 900:
            continue
        t = datetime.fromtimestamp(int(kv["ts"]), EST)
        hours[(t.strftime("%m-%d"), t.hour)].append(float(kv["load1"]))
    for (day, hour), v in sorted(hours.items()):
        print(f"{day} {hour:02d}h n={len(v):2d} median load1 {statistics.median(v):.2f}")


def watch_rows(path: str) -> list[dict]:
    return [m.groupdict() for m in map(WATCH.search, open(path, errors="replace")) if m]


def watch(path: str) -> None:
    rows = watch_rows(path)
    counts = Counter(r["rx"] for r in rows)
    print(f"samples {len(rows)}")
    for rate, n in sorted(counts.items(), key=lambda kv: -float(kv[0])):
        print(f"rx {rate:>5} MBit/s: {n}")
    fails = [int(r["fail"]) for r in rows]
    print(f"tx failed {min(fails)} -> {max(fails)}")
    print("rx below 19.5 at:", " ".join(r["t"] for r in rows if float(r["rx"]) < 19.5) or "none")


def pair(bench: str, prod: str, low: float) -> None:
    def by_bin(rows):
        out = {}
        for r in rows:
            h, m, s = map(int, r["t"].split(":"))
            out[(h * 3600 + m * 60 + s) // 10] = r
        return out

    b, p = by_bin(watch_rows(bench)), by_bin(watch_rows(prod))
    shared = sorted(set(b) & set(p))
    print(f"aligned 10 s bins: {len(shared)} (bench {len(b)}, prod {len(p)})")
    lows = {"bench": 0, "prod": 0, "both": 0}
    for k in shared:
        bl, pl = float(b[k]["rx"]) <= low, float(p[k]["rx"]) <= low
        lows["bench"] += bl
        lows["prod"] += pl
        lows["both"] += bl and pl
        if bl or pl:
            print(f"{b[k]['t']} bench rx {b[k]['rx']:>5} fail {b[k]['fail']:>4} | "
                  f"prod rx {p[k]['rx']:>5} fail {p[k]['fail']:>4}")
    print(f"bins at or below {low} MBit/s: bench {lows['bench']}, prod {lows['prod']}, both {lows['both']}")
    for name, rows in (("bench", b), ("prod", p)):
        f = [int(rows[k]["fail"]) for k in shared]
        print(f"{name} tx failed {f[0]} -> {f[-1]}" if f else f"{name}: no aligned samples")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "soak":
        soak(sys.argv[2])
    elif cmd == "watch":
        watch(sys.argv[2])
    elif cmd == "pair":
        pair(sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 6.5)
    else:
        sys.exit(__doc__)
