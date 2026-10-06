#!/usr/bin/env python3
"""analyze_burst2.py <run-dir>

Deterministic re-analysis of a burst (frame_NNN.ppm + timestamps.txt, one monotonic uptime float
per frame, written by run-burst-capture.sh). No step depends on a human or model looking at any
frame's content -- content hashes and arithmetic on them only.

Crop: kiosk-render-check.sh's own default, 560x300+220+20 (tools/kiosk-render-check.sh CROP=).

Revert definition: frame i's crop-hash equals frame (i-2)'s crop-hash, AND frame (i-1)'s hash
differs from frame i's -- i.e. a strict A,B,A triplet anchored two frames back. A run of
identical consecutive frames (A,A,A,...) is NOT a revert; the page is allowed to hold still.

For every revert, the "time span" is timestamps[i] - timestamps[i-2] (both in seconds, read from
the board's /proc/uptime at capture time) -- how long content was away before it came back.

Outputs, per run: distinct crop-hash count, revert count, revert time-span distribution
(min/median/max, and counts strictly under 1s/2s/4s), inter-capture interval stats
(median/max, computed from consecutive timestamp deltas).
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
        line = f.readline()
        while line.startswith(b"#"):
            line = f.readline()
        w, h = (int(x) for x in line.split())
        maxval = int(f.readline().strip())
        assert maxval == 255
        data = f.read(w * h * 3)
        return w, h, data


def crop(w, h, data, cw, ch, cx, cy):
    out = bytearray()
    for row in range(cy, cy + ch):
        start = (row * w + cx) * 3
        out += data[start:start + cw * 3]
    return bytes(out)


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def main(run_dir):
    CW, CH, CX, CY = 560, 300, 220, 20  # kiosk-render-check.sh's own default crop

    frames = sorted(glob.glob(os.path.join(run_dir, "frame_*.ppm")))
    if not frames:
        print(f"no frames found in {run_dir}", file=sys.stderr)
        sys.exit(2)

    ts_path = os.path.join(run_dir, "timestamps.txt")
    with open(ts_path) as f:
        timestamps = [float(l.strip()) for l in f if l.strip()]
    if len(timestamps) != len(frames):
        print(f"WARNING: {len(timestamps)} timestamps for {len(frames)} frames", file=sys.stderr)

    hashes = []
    for fp in frames:
        w, h, data = read_ppm(fp)
        c = crop(w, h, data, CW, CH, CX, CY)
        hashes.append(hashlib.sha256(c).hexdigest())

    distinct = len(set(hashes))

    reverts = []  # list of (frame_index_i, time_span)
    for i in range(2, len(hashes)):
        if hashes[i] == hashes[i - 2] and hashes[i - 1] != hashes[i]:
            span = timestamps[i] - timestamps[i - 2]
            reverts.append((i, span))

    intervals = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]

    print(f"=== {run_dir} ===")
    print(f"frames: {len(frames)}")
    print(f"crop: {CW}x{CH}+{CX}+{CY} (kiosk-render-check.sh default)")
    print(f"distinct crop-hash states: {distinct}")
    print(f"revert count (strict A,B,A anchored at i-2): {len(reverts)}")
    if reverts:
        spans = [s for _, s in reverts]
        under1 = sum(1 for s in spans if s < 1.0)
        under2 = sum(1 for s in spans if s < 2.0)
        under4 = sum(1 for s in spans if s < 4.0)
        print(f"revert time-span (s): min={min(spans):.3f} median={median(spans):.3f} max={max(spans):.3f}")
        print(f"  under 1s: {under1}  under 2s: {under2}  under 4s: {under4}  (of {len(reverts)} total)")
        print(f"  all spans: {[round(s,3) for s in spans]}")
        print(f"  revert frame indices (1-based): {[i+1 for i,_ in reverts]}")
    else:
        print("revert time-span (s): n/a (no reverts)")
    print(f"inter-capture interval (s): median={median(intervals):.3f} max={max(intervals):.3f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1])
