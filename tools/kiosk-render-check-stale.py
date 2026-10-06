#!/usr/bin/env python3
"""STALE verdict over bursts of kiosk-drmgrab --report captures.

    tools/kiosk-render-check-stale.py <manifest>

<manifest>: one line per capture, "fb_before=<id> fb_after=<id> ppm=<path>", in
capture order, bursts separated by blank lines. Prints "persistent tiles=<n>"
and exits 0 (no persistent tile), 3 (STALE) or 2 (could not tell).

The classifier of docs/issue_investigation/wpe_evaluation/analyze_burst_v3.py.
Per burst, over stable captures only (fb_before == fb_after) grouped by fb id in
first-seen order, and over whole 40x40-pixel tiles: a tile is testable when two
or more fb ids are present and each group's captures are byte-identical on it;
a testable tile disagrees when the first group's value differs from another's
by mean absolute byte difference > 1. A tile disagreeing in two consecutive
bursts is persistent; any persistent tile is STALE. A series of other than
EXPECTED_BURSTS bursts, a burst with fewer than two fb ids or no testable tile,
or any PPM that is malformed, truncated or of another size, is could-not-tell.
"""
import re
import sys

TILE = 40
EXPECTED_BURSTS = 6
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


def tile_bytes(w, data, tx, ty):
    x0, y0 = tx * TILE, ty * TILE
    out = bytearray()
    for row in range(y0, y0 + TILE):
        start = (row * w + x0) * 3
        out += data[start:start + TILE * 3]
    return bytes(out)


def mad(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def analyze_one_burst(stable_captures, w, h):
    """Returns (testable_tile_count, disagreeing_tile_set)."""
    cols, rows = w // TILE, h // TILE
    testable = 0
    disagreeing = set()
    for ty in range(rows):
        for tx in range(cols):
            ordered = [(fb, tile_bytes(w, data, tx, ty)) for fb, data in stable_captures]
            by_fb = {}
            for fb, tb in ordered:
                by_fb.setdefault(fb, []).append(tb)
            if len(by_fb) < 2:
                continue
            consistent = all(all(t == tiles[0] for t in tiles[1:]) for tiles in by_fb.values())
            if not consistent:
                continue
            testable += 1
            vals = [tiles[0] for tiles in by_fb.values()]
            if any(mad(vals[0], v) > 1 for v in vals[1:]):
                disagreeing.add((tx, ty))
    return testable, disagreeing


def stale_verdict(bursts):
    """{"rc": 0|2|3, "persistent_tiles": n} over bursts of captures, each in capture order."""
    cant_tell = {"rc": 2, "persistent_tiles": 0}
    frames = [[parse_ppm(c["ppm"]) for c in burst] for burst in bursts]
    flat = [f for burst in frames for f in burst]
    if len(bursts) != EXPECTED_BURSTS or not flat or any(f is None for f in flat) or len({f[:2] for f in flat}) > 1:
        return cant_tell
    w, h = flat[0][:2]

    per_burst = []
    for burst, parsed in zip(bursts, frames):
        stable = [(c["fb_before"], f[2]) for c, f in zip(burst, parsed)
                  if c["fb_before"] == c["fb_after"]]
        if len({fb for fb, _ in stable}) < 2:
            return cant_tell
        testable, disagreeing = analyze_one_burst(stable, w, h)
        if testable == 0:
            return cant_tell
        per_burst.append(disagreeing)

    persistent = set()
    for i in range(1, len(per_burst)):
        persistent |= per_burst[i] & per_burst[i - 1]
    return {"rc": 3 if persistent else 0, "persistent_tiles": len(persistent)}


LINE = re.compile(r"fb_before=(\d+) fb_after=(\d+) ppm=(\S+)$")


def main(argv):
    if len(argv) != 2:
        print("usage: kiosk-render-check-stale.py <manifest>", file=sys.stderr)
        print("persistent tiles=0")
        return 2
    bursts = [[]]
    try:
        with open(argv[1]) as manifest:
            for line in manifest:
                line = line.strip()
                if not line:
                    if bursts[-1]:
                        bursts.append([])
                    continue
                m = LINE.match(line)
                if not m:
                    raise ValueError(f"bad manifest line: {line!r}")
                with open(m.group(3), "rb") as ppm:
                    bursts[-1].append({"fb_before": int(m.group(1)),
                                       "fb_after": int(m.group(2)), "ppm": ppm.read()})
    except (OSError, ValueError) as e:
        print(f"kiosk-render-check-stale: {e}", file=sys.stderr)
        print("persistent tiles=0")
        return 2
    result = stale_verdict([b for b in bursts if b])
    print(f"persistent tiles={result['persistent_tiles']}")
    return result["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
