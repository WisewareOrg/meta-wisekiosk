#!/usr/bin/env python3
"""analyze_burst_v2.py <run-dir-1> [<run-dir-2> ...] [--nontrivial=N]

Deterministic, no image inspection. Concatenates one or more batch directories (each holding
frame_NNN.ppm, timestamps.txt, report.txt from run-burst-capture-v2.sh's --report mode) into one
time-ordered sequence, then reports, per combined run:

  - fb id sequence (fb_before,fb_after per frame, in order)
  - distinct fb id count (union of fb_before and fb_after values seen)
  - count of captures with fb_before != fb_after (a tear/buffer-swap mid-capture)
  - copy_ms median/max
  - revert stats (hash[i]==hash[i-2], hash[i-1] differs; render-check crop 560x300+220+20),
    split into two counts: reverts where the capture was "stable" (fb_before==fb_after) and
    reverts where it was not

A frame whose report.txt line doesn't match the "fb_before=<id> fb_after=<id> copy_ms=<int>"
format (a capture failure, or built against a kiosk-drmgrab without --report) is marked
unparsed and excluded from the fb-id/copy_ms stats, but still included in the hash/revert stats
if its PPM exists and is readable.

Since exact-match reverts are rare at this crop size (see full_cross_match.py's clean-negative
result), also reports a near-revert signal: for each frame i, the mean absolute pixel difference
(full, unsampled, over the render-check crop) to frame i-1 and to frame i-2. Frame i is flagged
when d(i,i-2) < d(i,i-1)/4 while d(i,i-1) is "non-trivial" -- above --nontrivial (default 2.0, same
0-255 units as the diff itself; stated explicitly in the output since the threshold is an analysis
choice, not a documented constant). Reports the flagged count and the d(i,i-2)/d(i,i-1) ratio
distribution (min/median/max) over every i with d(i,i-1) > 0.
"""
import sys, re, hashlib, glob, os

sys.path.insert(0, os.path.dirname(__file__))
from analyze_burst import read_ppm, crop as crop_fn

RC_CROP = (560, 300, 220, 20)
REPORT_RE = re.compile(r"fb_before=(\S+)\s+fb_after=(\S+)\s+copy_ms=(\d+)")


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def full_mean_abs_diff(a, b):
    """Unsampled mean absolute byte difference -- small enough crop (504,000 bytes) that this is
    cheap, and the ratio test needs the real value, not a strided estimate."""
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def load_batch(batch_dir):
    frames = sorted(glob.glob(os.path.join(batch_dir, "frame_*.ppm")))
    with open(os.path.join(batch_dir, "timestamps.txt")) as f:
        ts = [float(l.strip()) for l in f if l.strip()]
    reports = {}
    report_path = os.path.join(batch_dir, "report.txt")
    if os.path.exists(report_path):
        with open(report_path) as f:
            for line in f:
                m = re.match(r"FRAME (\d+): (.*)", line.strip())
                if m:
                    reports[int(m.group(1))] = m.group(2)
    return frames, ts, reports


def main(batch_dirs, nontrivial=2.0):
    all_frames, all_ts, all_reports = [], [], []
    for bd in batch_dirs:
        frames, ts, reports = load_batch(bd)
        base = len(all_frames)
        all_frames.extend(frames)
        all_ts.extend(ts)
        for idx1, text in reports.items():
            all_reports.append((base + idx1 - 1, text))  # 0-based index into the combined list

    report_by_idx = dict(all_reports)
    n = len(all_frames)
    print(f"=== {batch_dirs} combined: {n} frames ===")

    hashes = []
    crops = []
    fb_before, fb_after, copy_ms, stable = [], [], [], []
    unparsed = 0
    for i, fp in enumerate(all_frames):
        w, h, data = read_ppm(fp)
        c = crop_fn(w, h, data, *RC_CROP)
        crops.append(c)
        hashes.append(hashlib.sha256(c).hexdigest())
        text = report_by_idx.get(i, "")
        m = REPORT_RE.search(text)
        if m:
            b, a, ms = m.group(1), m.group(2), int(m.group(3))
            fb_before.append(b)
            fb_after.append(a)
            copy_ms.append(ms)
            stable.append(b == a)
        else:
            fb_before.append(None)
            fb_after.append(None)
            copy_ms.append(None)
            stable.append(None)
            unparsed += 1

    distinct_fb = set(x for x in fb_before + fb_after if x is not None)
    print(f"unparsed report lines: {unparsed} / {n}")
    print(f"distinct fb ids seen: {len(distinct_fb)}: {sorted(distinct_fb)}")
    tear_count = sum(1 for b, a in zip(fb_before, fb_after) if b is not None and b != a)
    print(f"captures with fb_before != fb_after: {tear_count}")
    valid_ms = [m for m in copy_ms if m is not None]
    if valid_ms:
        print(f"copy_ms: median={median(valid_ms):.1f} max={max(valid_ms)}")
    else:
        print("copy_ms: no parsed samples")
    print(f"fb id sequence (before,after): {[(b,a) for b,a in zip(fb_before, fb_after)]}")

    reverts_stable, reverts_unstable, reverts_unknown = 0, 0, 0
    for i in range(2, n):
        if hashes[i] == hashes[i - 2] and hashes[i - 1] != hashes[i]:
            s = stable[i]
            if s is True:
                reverts_stable += 1
            elif s is False:
                reverts_unstable += 1
            else:
                reverts_unknown += 1
    print(f"reverts: stable-capture={reverts_stable} unstable-capture={reverts_unstable} unknown(unparsed)={reverts_unknown}")

    print(f"-- near-revert ratio signal (nontrivial threshold = {nontrivial}) --")
    ratios = []
    flagged = []
    for i in range(2, n):
        d1 = full_mean_abs_diff(crops[i], crops[i - 1])
        d2 = full_mean_abs_diff(crops[i], crops[i - 2])
        if d1 > 0:
            ratios.append(d2 / d1)
        if d1 > nontrivial and d2 < d1 / 4:
            flagged.append((i, d1, d2, d2 / d1 if d1 > 0 else float("nan")))
    if ratios:
        print(f"d(i,i-2)/d(i,i-1) ratio: min={min(ratios):.4f} median={median(ratios):.4f} max={max(ratios):.4f} (n={len(ratios)})")
    else:
        print("ratio: no pairs with d(i,i-1) > 0")
    flagged_stable = sum(1 for i, *_ in flagged if stable[i] is True)
    flagged_unstable = sum(1 for i, *_ in flagged if stable[i] is False)
    flagged_unknown = sum(1 for i, *_ in flagged if stable[i] is None)
    print(f"flagged frames (d(i,i-1) > {nontrivial} and d(i,i-2) < d(i,i-1)/4): {len(flagged)} "
          f"(stable-capture={flagged_stable} unstable-capture={flagged_unstable} unknown(unparsed)={flagged_unknown})")
    for i, d1, d2, r in flagged:
        print(f"   frame {i+1} (t={all_ts[i]:.3f}, stable={stable[i]}): d(i,i-1)={d1:.3f} d(i,i-2)={d2:.3f} ratio={r:.4f}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--nontrivial=")]
    nt_args = [a for a in sys.argv[1:] if a.startswith("--nontrivial=")]
    nontrivial = float(nt_args[0].split("=", 1)[1]) if nt_args else 2.0
    if len(args) < 1:
        print(__doc__)
        sys.exit(2)
    main(args, nontrivial=nontrivial)
