#!/usr/bin/env python3
"""STALE verdict over a series of kiosk-drmgrab --report captures.

    tools/kiosk-render-check-stale.py <manifest>

<manifest>: one line per capture, in capture order,
"fb_before=<id> fb_after=<id> ppm=<path>". Prints "stale tiles=<n>" and exits
0 (no stale tile), 3 (STALE) or 2 (could not tell).

Only stable captures count (fb_before == fb_after), grouped by fb id. The frame
is cut into 40x40-pixel tiles, edge tiles partial; MAD is the mean absolute
byte difference over a tile's RGB bytes. A tile is stale when, for two fbs that
each have at least two stable captures, every capture of each fb matches that
fb's first (MAD <= 1) and the two fbs' first captures differ (MAD > 1). Two fb
ids in a single chronological split are a one-time repaint and pass. One fb id
passes. Fewer than two stable captures, two or more fb ids but fewer than two
fbs with two stable captures each, or any PPM that is malformed, truncated or
of another size, is could-not-tell.
"""
import re
import sys
from itertools import combinations

TILE = 40
HEADER = re.compile(rb"P6\s+(\d+)\s+(\d+)\s+(\d+)\s")


def parse_ppm(data):
    """(width, height, rgb bytes) of a binary PPM, or None if malformed or truncated."""
    m = HEADER.match(data)
    if not m or int(m.group(3)) != 255:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    rgb = data[m.end():]
    if w == 0 or h == 0 or len(rgb) != w * h * 3:
        return None
    return w, h, rgb


def tiles(w, h):
    """(x0, y0, x1, y1) of every 40x40-pixel tile, edge tiles clipped to the frame."""
    return [(x, y, min(x + TILE, w), min(y + TILE, h))
            for y in range(0, h, TILE) for x in range(0, w, TILE)]


def tile_mad(a, b, w, tile):
    x0, y0, x1, y1 = tile
    total = 0
    for y in range(y0, y1):
        lo, hi = (y * w + x0) * 3, (y * w + x1) * 3
        ra, rb = a[lo:hi], b[lo:hi]
        if ra != rb:
            total += sum(abs(p - q) for p, q in zip(ra, rb))
    return total / ((x1 - x0) * (y1 - y0) * 3)


def single_split(ids):
    """True when the id sequence holds exactly two ids, all of one before all of the other."""
    changes = sum(1 for p, q in zip(ids, ids[1:]) if p != q)
    return len(set(ids)) == 2 and changes == 1


def stale_verdict(captures):
    """{"rc": 0|2|3, "stale_tiles": n} over captures in capture order."""
    cant_tell = {"rc": 2, "stale_tiles": 0}
    frames = [parse_ppm(c["ppm"]) for c in captures]
    if any(f is None for f in frames) or len({f[:2] for f in frames}) > 1:
        return cant_tell

    stable = [(c["fb_before"], f[2]) for c, f in zip(captures, frames)
              if c["fb_before"] == c["fb_after"]]
    ids = [fb for fb, _ in stable]
    if len(stable) < 2:
        return cant_tell
    if len(set(ids)) <= 1:
        return {"rc": 0, "stale_tiles": 0}

    groups = {}
    for fb, rgb in stable:
        groups.setdefault(fb, []).append(rgb)
    eligible = [fb for fb in groups if len(groups[fb]) >= 2]
    if len(eligible) < 2:
        return cant_tell
    if single_split(ids):
        return {"rc": 0, "stale_tiles": 0}

    w, h = frames[0][:2]
    grid = tiles(w, h)
    steady = {fb: {t for t in grid
                   if all(tile_mad(groups[fb][0], other, w, t) <= 1 for other in groups[fb][1:])}
              for fb in eligible}
    stale = set()
    for a, b in combinations(eligible, 2):
        for t in steady[a] & steady[b]:
            if t not in stale and tile_mad(groups[a][0], groups[b][0], w, t) > 1:
                stale.add(t)
    return {"rc": 3 if stale else 0, "stale_tiles": len(stale)}


LINE = re.compile(r"fb_before=(\d+) fb_after=(\d+) ppm=(\S+)$")


def main(argv):
    if len(argv) != 2:
        print("usage: kiosk-render-check-stale.py <manifest>", file=sys.stderr)
        print("stale tiles=0")
        return 2
    captures = []
    try:
        with open(argv[1]) as manifest:
            for line in manifest:
                line = line.strip()
                if not line:
                    continue
                m = LINE.match(line)
                if not m:
                    raise ValueError(f"bad manifest line: {line!r}")
                with open(m.group(3), "rb") as ppm:
                    captures.append({"fb_before": int(m.group(1)),
                                     "fb_after": int(m.group(2)), "ppm": ppm.read()})
    except (OSError, ValueError) as e:
        print(f"kiosk-render-check-stale: {e}", file=sys.stderr)
        print("stale tiles=0")
        return 2
    result = stale_verdict(captures)
    print(f"stale tiles={result['stale_tiles']}")
    return result["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
