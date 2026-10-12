#!/usr/bin/env python3
"""analyze_fw_burst.py <label> <mode: fw|drm> <batch-dir-1> [<batch-dir-2> ...]

Deterministic, no image inspection by eye. Each <batch-dir> is one run-fw-burst-capture.sh
batch of back-to-back captures from a single tool (kiosk-fwgrab or kiosk-drmgrab), in order.

Splits each frame into a fixed 40x40-pixel tile grid at THAT TOOL's own native resolution
(read from its own PPM header -- not assumed). For each tile and each frame i (i>=2 within
the concatenated sequence), a "flip" is: mean_abs_diff(tile[i-2], tile[i]) <= 1 AND
mean_abs_diff(tile[i-1], tile[i]) > 4 -- the tile went A,B,A, i.e. briefly changed and changed
back within one frame.

Reports: total flip count, count of tiles with >=3 flips over the whole run, count of frames
with any flip, and the top 10 flip tiles by count. For mode=fw also the per-capture ms
(timed externally, from report.txt) median/max; for mode=drm, kiosk-drmgrab's own copy_ms
median/max from its --report line.

Every batch is expected to hold BATCH_EXPECTED frames. A batch that lost frames (a failed
transfer, a truncated file) is VOID: labelled, excluded WHOLE from the concatenated sequence --
not just its missing frames -- because flip detection depends on i-2/i-1/i being truly
consecutive, and splicing across a gap would compare unrelated frames as if adjacent.
"""
import sys, re, glob, os

sys.path.insert(0, os.path.dirname(__file__))
from analyze_burst import read_ppm

TILE = 40
DRM_RE = re.compile(r"fb_before=(\S+)\s+fb_after=(\S+)\s+copy_ms=(\d+)")
FW_RE = re.compile(r"rc=(\d+)\s+ms=(\d+)")
BATCH_EXPECTED = 30


def load_batch(batch_dir, mode):
    """Returns (frames_found, frame_list). frame_list is the full batch's frames if complete,
    else [] -- a short batch contributes nothing to the sequence, it is not partially used."""
    frames = sorted(glob.glob(os.path.join(batch_dir, "frame_*.ppm")))
    reports = {}
    report_path = os.path.join(batch_dir, "report.txt")
    if os.path.exists(report_path):
        with open(report_path) as f:
            for line in f:
                m = re.match(r"FRAME (\d+)[: ]*(.*)", line.strip())
                if m:
                    reports.setdefault(int(m.group(1)), m.group(2))
    out = []  # list of (w, h, data, timing_value_or_None)
    frames_found = 0
    for idx, fp in enumerate(frames, start=1):
        try:
            w, h, data = read_ppm(fp)
        except (ValueError, AssertionError) as e:
            print(f"    frame {idx} ({fp}) unreadable, not counted as found: {e}")
            continue
        frames_found += 1
        text = reports.get(idx, "")
        timing = None
        if mode == "fw":
            m = FW_RE.search(text)
            if m:
                timing = int(m.group(2))
        else:
            m = DRM_RE.search(text)
            if m:
                timing = int(m.group(3))
        out.append((w, h, data, timing))
    if frames_found < BATCH_EXPECTED:
        print(f"  {batch_dir}: VOID -- frames_found={frames_found}/{BATCH_EXPECTED}, "
              f"whole batch excluded")
        return frames_found, []
    return frames_found, out


def tile_bytes(w, h, data, tx, ty):
    x0, y0 = tx * TILE, ty * TILE
    out = bytearray()
    for row in range(y0, y0 + TILE):
        start = (row * w + x0) * 3
        out += data[start:start + TILE * 3]
    return bytes(out)


def mad(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def main(label, mode, batch_dirs):
    seq = []
    void_batches = 0
    for bd in batch_dirs:
        frames_found, frames = load_batch(bd, mode)
        if not frames:
            void_batches += 1
        seq.extend(frames)
    if void_batches:
        print(f"-- {void_batches}/{len(batch_dirs)} batch(es) VOID (lost frames), excluded above")
    n = len(seq)
    if n == 0:
        print(f"=== {label} ({mode}): 0 usable frames (all batches VOID) -- VERDICT: VOID, no result ===")
        return
    ws = {w for w, h, d, t in seq}
    hs = {h for w, h, d, t in seq}
    print(f"=== {label} ({mode}): {n} frames, native dims seen: W={sorted(ws)} H={sorted(hs)} ===")
    if len(ws) != 1 or len(hs) != 1:
        print("  WARNING: frames are not all the same size; proceeding with the first frame's dims")
    w0, h0 = seq[0][0], seq[0][1]
    cols, rows = w0 // TILE, h0 // TILE
    print(f"  tile grid {cols}x{rows} ({cols * rows} tiles)")

    flip_counts = {}  # (tx,ty) -> count
    frames_with_flip = set()
    total_flips = 0

    # pre-extract all tiles for all frames once (frame_idx -> {(tx,ty): bytes})
    tiles_per_frame = []
    for w, h, data, _ in seq:
        tiles = {}
        for ty in range(rows):
            for tx in range(cols):
                tiles[(tx, ty)] = tile_bytes(w, h, data, tx, ty)
        tiles_per_frame.append(tiles)

    for i in range(2, n):
        frame_flipped = False
        for ty in range(rows):
            for tx in range(cols):
                t_im2 = tiles_per_frame[i - 2][(tx, ty)]
                t_im1 = tiles_per_frame[i - 1][(tx, ty)]
                t_i = tiles_per_frame[i][(tx, ty)]
                d1 = mad(t_im1, t_i)
                d2 = mad(t_im2, t_i)
                if d2 <= 1 and d1 > 4:
                    flip_counts[(tx, ty)] = flip_counts.get((tx, ty), 0) + 1
                    total_flips += 1
                    frame_flipped = True
        if frame_flipped:
            frames_with_flip.add(i)

    persistent = sorted(((c, xy) for xy, c in flip_counts.items() if c >= 3), reverse=True)
    top10 = sorted(flip_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

    print(f"  total flips: {total_flips}")
    print(f"  tiles with >=3 flips: {len(persistent)}")
    print(f"  frames with any flip: {len(frames_with_flip)} / {n - 2} comparable")
    print(f"  top 10 flip tiles (coord: count): {[(xy, c) for xy, c in top10]}")

    timings = [t for _, _, _, t in seq if t is not None]
    if timings:
        s = sorted(timings)
        med = s[len(s) // 2]
        label_t = "ms" if mode == "fw" else "copy_ms"
        print(f"  {label_t}: median={med} max={max(s)} n={len(s)}")
    else:
        print("  (no timing values parsed)")


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[2] not in ("fw", "drm"):
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
