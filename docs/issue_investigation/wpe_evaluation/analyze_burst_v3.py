#!/usr/bin/env python3
"""analyze_burst_v3.py <label> <burst-dir-1> [<burst-dir-2> ...]

Deterministic, no image inspection, no hand-picked regions. Each <burst-dir> is one
run-burst-capture-v3.sh burst (15 frames, timestamps.txt, report.txt with --report lines).
Burst dirs are re-sorted here by the trailing -N in their own name (not by command-line
order and not lexically: lexical sort puts control-10 before control-2), so the "over time"
series is always in actual burst order regardless of how the caller passed them.

Splits the full 1280x720 frame into a fixed 40x40-pixel tile grid (32 cols x 18 rows = 576
tiles). Per burst: among STABLE captures only (fb_before == fb_after, parsed from report.txt),
in chronological order. For each tile, checks whether all of a given fb's stable captures in
this burst agree on that tile's content (self-consistency); if both fb groups present and
self-consistent on a tile, the tile "disagrees" this burst when mean_abs_diff(fb_A_tile,
fb_B_tile) > 1. A burst with fewer than two distinct stable fb ids cannot test any tile.

For every disagreeing tile, also checks whether it is a LATE-CHANGE ARTIFACT: across the
full chronological sequence of stable captures (both fb groups combined), the tile's content
changes at most once, and that one change point exactly separates "all of one fb" from "all
of the other" -- i.e. the apparent fb-vs-fb disagreement is fully explained by the content
legitimately changing once mid-burst, with the two fb groups happening to fall on either side
of that change, rather than by a persistent per-buffer split.

Prints, per burst: disagreeing-tile count, and that count again with late-change artifacts
excluded. At the end: every tile disagreeing in >=2 CONSECUTIVE bursts, grouped into
contiguous (4-connected) bounding boxes rather than listed tile-by-tile.

A burst that lost frames (a failed transfer, a truncated file) is VOID: it is labelled, printed
with its frames_found/frames_expected count, and excluded from the series and from every
consecutive-burst check -- never scored as "0 disagreement".
"""
import sys, re, glob, os

sys.path.insert(0, os.path.dirname(__file__))
from analyze_burst import read_ppm

TILE = 40
REPORT_RE = re.compile(r"fb_before=(\S+)\s+fb_after=(\S+)\s+copy_ms=(\d+)")

# Every run-burst-capture-v3*.sh / run-v3-short.sh burst is 15 frames. A burst that lost frames
# to a failed transfer (tar hitting "no space left on device" mid-write, an interrupted scp)
# must never be silently scored as if it had fewer legitimate captures -- it is VOID.
FRAMES_EXPECTED = 15


def natural_sort_key(path):
    m = re.search(r"-(\d+)/?$", path.rstrip("/"))
    return int(m.group(1)) if m else path


def load_burst(burst_dir):
    """Returns (frames_found, stable_captures). frames_found counts every frame_NNN.ppm that
    exists AND reads back as a complete, correctly-sized frame -- a truncated file (short read,
    now rejected by read_ppm) does not count as found, regardless of whether it would have been
    stable or unstable."""
    frames = sorted(glob.glob(os.path.join(burst_dir, "frame_*.ppm")))
    reports = {}
    report_path = os.path.join(burst_dir, "report.txt")
    if os.path.exists(report_path):
        with open(report_path) as f:
            for line in f:
                m = re.match(r"FRAME (\d+): (.*)", line.strip())
                if m:
                    reports[int(m.group(1))] = m.group(2)
    frames_found = 0
    out = []  # list of (fb_id, w, h, data), in chronological (frame) order, stable only
    for idx, fp in enumerate(frames, start=1):
        try:
            w, h, data = read_ppm(fp)
        except (ValueError, AssertionError) as e:
            print(f"    frame {idx} ({fp}) unreadable, not counted as found: {e}")
            continue
        frames_found += 1
        text = reports.get(idx, "")
        m = REPORT_RE.search(text)
        if not m:
            continue
        b, a = m.group(1), m.group(2)
        if b != a:
            continue  # unstable capture, excluded from the disagreement test (not a loss)
        out.append((b, w, h, data))
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


def is_late_change_artifact(ordered_fb_tiles):
    """ordered_fb_tiles: [(fb, tile_bytes), ...] in chronological order. True iff content
    changes at most once and that change point cleanly separates the two fb groups."""
    change_indices = [i for i in range(1, len(ordered_fb_tiles))
                       if ordered_fb_tiles[i][1] != ordered_fb_tiles[i - 1][1]]
    if len(change_indices) != 1:
        return False
    c = change_indices[0]
    fbs_before = {fb for fb, _ in ordered_fb_tiles[:c]}
    fbs_after = {fb for fb, _ in ordered_fb_tiles[c:]}
    return len(fbs_before) == 1 and len(fbs_after) == 1 and fbs_before != fbs_after


def analyze_one_burst(stable_captures):
    """Returns (testable_tile_count, disagreeing_tile_set, late_change_tile_set)."""
    cols, rows = 1280 // TILE, 720 // TILE
    testable = 0
    disagreeing = set()
    late_change = set()
    for ty in range(rows):
        for tx in range(cols):
            ordered = [(fb, tile_bytes(w, h, data, tx, ty)) for fb, w, h, data in stable_captures]
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
                if is_late_change_artifact(ordered):
                    late_change.add((tx, ty))
    return testable, disagreeing, late_change


def bounding_boxes(tiles):
    """4-connected components of a coordinate set, each reported as its bounding box."""
    remaining = set(tiles)
    boxes = []
    while remaining:
        start = next(iter(remaining))
        stack = [start]
        comp = set()
        remaining.discard(start)
        while stack:
            cur = stack.pop()
            comp.add(cur)
            x, y = cur
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in remaining:
                    remaining.discard(nb)
                    stack.append(nb)
        xs = [x for x, y in comp]
        ys = [y for x, y in comp]
        boxes.append(((min(xs), min(ys)), (max(xs), max(ys)), len(comp)))
    return sorted(boxes)


def main(label, burst_dirs):
    burst_dirs = sorted(burst_dirs, key=natural_sort_key)
    print(f"=== {label}: {len(burst_dirs)} bursts (natural order), tile grid {1280//TILE}x{720//TILE} "
          f"({(1280//TILE)*(720//TILE)} tiles), frames expected per burst: {FRAMES_EXPECTED} ===")
    # None marks a VOID burst (lost frames): excluded from the series and from every
    # consecutive-pair check below, never silently read as "0 disagreement".
    per_burst_disagreeing = []
    per_burst_excl_late = []
    void_count = 0
    for n, bd in enumerate(burst_dirs, start=1):
        frames_found, stable = load_burst(bd)
        if frames_found < FRAMES_EXPECTED:
            void_count += 1
            per_burst_disagreeing.append(None)
            per_burst_excl_late.append(None)
            print(f"  burst {n} ({bd}): VOID -- frames_found={frames_found}/{FRAMES_EXPECTED}, "
                  f"excluded from the series")
            continue
        testable, disagreeing, late_change = analyze_one_burst(stable)
        per_burst_disagreeing.append(disagreeing)
        per_burst_excl_late.append(disagreeing - late_change)
        print(f"  burst {n} ({bd}): frames_found={frames_found}/{FRAMES_EXPECTED} "
              f"stable_captures={len(stable)} testable_tiles={testable} "
              f"disagreeing_tiles={len(disagreeing)} late_change_artifacts={len(late_change)} "
              f"disagreeing_excl_late_change={len(disagreeing - late_change)}")

    series = ["VOID" if d is None else len(d) for d in per_burst_disagreeing]
    series_excl = ["VOID" if d is None else len(d) for d in per_burst_excl_late]
    print(f"-- disagreeing-tile count over time: {series}")
    print(f"-- disagreeing-tile count over time, late-change artifacts excluded: {series_excl}")
    if void_count:
        print(f"-- {void_count}/{len(burst_dirs)} burst(s) VOID (lost frames), excluded above")

    persistent = set()
    persistent_excl = set()
    for i in range(1, len(per_burst_disagreeing)):
        a, b = per_burst_disagreeing[i], per_burst_disagreeing[i - 1]
        if a is not None and b is not None:
            persistent |= (a & b)
        a2, b2 = per_burst_excl_late[i], per_burst_excl_late[i - 1]
        if a2 is not None and b2 is not None:
            persistent_excl |= (a2 & b2)
    print(f"-- tiles disagreeing in >=2 CONSECUTIVE bursts: {len(persistent)}")
    if persistent:
        print(f"   bounding boxes (tx,ty)-(tx,ty): tile_count: {bounding_boxes(persistent)}")
    print(f"-- same, late-change artifacts excluded: {len(persistent_excl)}")
    if persistent_excl:
        print(f"   bounding boxes (tx,ty)-(tx,ty): tile_count: {bounding_boxes(persistent_excl)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2:])
