#!/usr/bin/env python3
"""Parse gpu_compositing/p7_min.js's MP| payload into the #185 smoothness statistics.

  python3 parse_smoothness.py <capture>   report the last MP| line in a capture

Payload, statistics and their definitions: parse_smoothness_test.py's header.
"""
import re
import sys

PAT = re.compile(r"MP\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|H(\d+(?:\.\d+){6})\|B([\d.:,]*)")
BIG = re.compile(r"^(\d+(?:\.\d+)?):(\d+)$")


def parse(line):
    """One MP| payload line -> dict, or None if the line holds no complete payload."""
    m = PAT.search(line)
    if not m:
        return None
    big = []
    for e in filter(None, m.group(7).split(",")):
        b = BIG.match(e)
        if not b:
            return None
        big.append((float(b.group(1)), int(b.group(2))))
    sec, frames, avg, mx, bt = (int(m.group(i)) for i in range(1, 6))
    return {"sec": sec, "frames": frames, "avg": avg, "max": mx, "bt": bt,
            "hist": [int(x) for x in m.group(6).split(".")], "big": big}


def pct_under_50ms(d):
    return 100.0 * d["hist"][0] / sum(d["hist"])


def mean_fps(d):
    return d["frames"] / d["sec"]


def steady_stall_rate(d, steady_from=15.0):
    return sum(1 for t, _ in d["big"] if t >= steady_from) / (d["sec"] - steady_from)


def clusters(d, gap=1.0):
    out = []
    for e in d["big"]:
        if out and e[0] - out[-1][-1][0] <= gap:
            out[-1].append(e)
        else:
            out.append([e])
    return out


def main(path):
    lines = [l for l in open(path).read().replace('"', "").splitlines() if "MP|" in l]
    d = parse(lines[-1]) if lines else None
    if d is None:
        sys.exit(f"no complete MP| payload in {path}")
    print(f"window {d['sec']} s  frames {d['frames']}  bt {d['bt']}  big[] {len(d['big'])}")
    print(f"mean fps          {mean_fps(d):.2f}")
    print(f"% frames <50 ms   {pct_under_50ms(d):.1f}")
    print(f"stall rate t>=15  {steady_stall_rate(d):.4f}/s")
    print(f"clusters          {[len(c) for c in clusters(d)]}")


if __name__ == "__main__":
    main(sys.argv[1])
