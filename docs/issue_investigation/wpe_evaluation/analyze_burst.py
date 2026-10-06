#!/usr/bin/env python3
"""analyze_burst.py <run-dir> <region-name>=<W>x<H>+<X>+<Y> [...]

Reads a burst of P6 PPM frames (frame_NNN.ppm) from <run-dir>, plus timestamps.txt (one
monotonic uptime float per frame, same order). For each named region, per frame: a content hash
(sha256 of the cropped pixel bytes) and the mean absolute pixel difference to the PREVIOUS frame.

A "revert" at frame i is: region[i] content-hash equals region[j] for some j < i-1, while
region[i-1] != region[i] (i.e. A,B,A -- not simple A,A,A steadiness). Reports, per region: the
count of distinct states seen, the revert count, and whether frames alternate strictly between
exactly two states (every frame's hash is one of exactly 2 values, alternating every frame).

No external deps (stdlib only: can read PPM P6 by hand).
"""
import sys
import hashlib
import glob
import os


def read_ppm(path):
    with open(path, "rb") as f:
        magic = f.readline().strip()
        if magic != b"P6":
            raise ValueError(f"{path}: not P6")
        # skip comments
        line = f.readline()
        while line.startswith(b"#"):
            line = f.readline()
        w, h = (int(x) for x in line.split())
        maxval = int(f.readline().strip())
        assert maxval == 255
        data = f.read(w * h * 3)
        if len(data) != w * h * 3:
            # A truncated transfer (tar hitting "no space left on device" mid-write, an
            # interrupted scp) leaves a short file that silently reads as fewer pixels than
            # claimed -- every caller must see this as a missing frame, never as valid data.
            raise ValueError(f"{path}: truncated, {len(data)} bytes, expected {w * h * 3}")
        return w, h, data


def crop(w, h, data, cw, ch, cx, cy):
    out = bytearray()
    for row in range(cy, cy + ch):
        start = (row * w + cx) * 3
        out += data[start:start + cw * 3]
    return bytes(out)


def mean_abs_diff(a, b):
    n = len(a)
    if n == 0:
        return 0.0
    s = 0
    for i in range(0, n, 997):  # sample every 997th byte for speed; stride is prime, covers RGB evenly over many frames
        s += abs(a[i] - b[i])
    count = len(range(0, n, 997))
    return s / count if count else 0.0


def main(run_dir, region_specs):
    regions = {}
    for spec in region_specs:
        name, geom = spec.split("=")
        wh, xy = geom.split("+", 1)
        w, h = (int(x) for x in wh.split("x"))
        x, y = (int(x) for x in xy.split("+"))
        regions[name] = (w, h, x, y)

    frames = sorted(glob.glob(os.path.join(run_dir, "frame_*.ppm")))
    if not frames:
        print(f"no frames found in {run_dir}", file=sys.stderr)
        sys.exit(2)

    ts_path = os.path.join(run_dir, "timestamps.txt")
    timestamps = []
    if os.path.exists(ts_path):
        with open(ts_path) as f:
            timestamps = [float(l.strip()) for l in f if l.strip()]

    print(f"=== {run_dir}: {len(frames)} frames ===")

    per_region_hashes = {name: [] for name in regions}
    per_region_raw = {name: [] for name in regions}

    fw = fh = None
    for fp in frames:
        w, h, data = read_ppm(fp)
        fw, fh = w, h
        for name, (cw, ch, cx, cy) in regions.items():
            c = crop(w, h, data, cw, ch, cx, cy)
            per_region_hashes[name].append(hashlib.sha256(c).hexdigest()[:12])
            per_region_raw[name].append(c)

    if timestamps:
        print(f"capture span: {timestamps[-1] - timestamps[0]:.2f}s over {len(timestamps)} frames, "
              f"mean interval {((timestamps[-1]-timestamps[0])/(len(timestamps)-1)):.3f}s")

    for name in regions:
        hashes = per_region_hashes[name]
        raws = per_region_raw[name]
        distinct = len(set(hashes))
        reverts = 0
        seen_before_prev = set()
        for i in range(2, len(hashes)):
            if hashes[i] != hashes[i-1] and hashes[i] in hashes[:i-1]:
                reverts += 1
        # strict two-state alternation check
        uniq = list(dict.fromkeys(hashes))  # preserve order of first occurrence
        alternates = False
        if len(uniq) == 2:
            a, b = uniq
            alternates = all(hashes[i] == (a if i % 2 == hashes.index(a) % 2 else b) for i in range(len(hashes))) or \
                         all((hashes[i] == a) == (i % 2 == 0) for i in range(len(hashes))) or \
                         all((hashes[i] == b) == (i % 2 == 0) for i in range(len(hashes)))
        diffs = [mean_abs_diff(raws[i], raws[i-1]) for i in range(1, len(raws))]
        print(f"  region {name} {regions[name]}: distinct_states={distinct} reverts={reverts} "
              f"strict_2state_alternation={alternates} mean_abs_diff(min/mean/max)="
              f"{min(diffs):.2f}/{sum(diffs)/len(diffs):.2f}/{max(diffs):.2f}")
        print(f"    hash sequence: {' '.join(hashes)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2:])
