#!/usr/bin/env python3
"""full_cross_match.py -- offline, mechanical only (sha256 of raw bytes, no image opened).

For every frame in BOTH runs, computes:
  - full-frame hash (the entire 1280x720 PPM pixel payload)
  - render-check-crop hash (560x300+220+20, kiosk-render-check.sh's own default)

Reports:
  1. Cross-run matches: every (cpu_idx -> control_idx) pair whose full-frame hash is equal, and
     separately every pair whose render-check-crop hash is equal, each with both frames'
     timestamps.
  2. Within-run full-frame matches at ANY distance: frame i equals some earlier frame j < i-1,
     with at least one frame strictly between j and i whose hash differs from both (so a long run
     of i,i+1,i+2,... all identical is one event, not one per step) -- distance reported in frames
     and seconds.
"""
import sys, hashlib, glob, os

sys.path.insert(0, os.path.dirname(__file__))
from analyze_burst import read_ppm, crop as crop_fn

RC_CROP = (560, 300, 220, 20)


def load(run_dir):
    frames = sorted(glob.glob(os.path.join(run_dir, "frame_*.ppm")))
    with open(os.path.join(run_dir, "timestamps.txt")) as f:
        ts = [float(l.strip()) for l in f if l.strip()]
    full_h, rc_h = [], []
    for fp in frames:
        w, h, data = read_ppm(fp)
        full_h.append(hashlib.sha256(data).hexdigest())
        c = crop_fn(w, h, data, *RC_CROP)
        rc_h.append(hashlib.sha256(c).hexdigest())
    return full_h, rc_h, ts


def cross_matches(h_a, ts_a, h_b, ts_b, label):
    print(f"-- cross-run matches, {label} --")
    found = 0
    for i, ha in enumerate(h_a):
        for j, hb in enumerate(h_b):
            if ha == hb:
                print(f"   cpu[{i+1}] (t={ts_a[i]:.3f}) == control[{j+1}] (t={ts_b[j]:.3f})")
                found += 1
    if not found:
        print("   none")


def within_run_matches(hashes, ts, label):
    print(f"-- within-run matches at any distance (j<i-1, a differing frame between), {label} --")
    found = 0
    n = len(hashes)
    for i in range(n):
        for j in range(i - 1):  # j < i-1, i.e. j ranges 0..i-2
            if hashes[i] != hashes[j]:
                continue
            # require at least one differing frame strictly between j and i
            if not any(hashes[k] != hashes[j] for k in range(j + 1, i)):
                continue
            dist_frames = i - j
            dist_s = ts[i] - ts[j]
            print(f"   frame {i+1} (t={ts[i]:.3f}) == frame {j+1} (t={ts[j]:.3f}): "
                  f"distance {dist_frames} frames, {dist_s:.3f}s")
            found += 1
    if not found:
        print("   none")


def main():
    cpu_full, cpu_rc, cpu_ts = load("data/cpu")
    ctl_full, ctl_rc, ctl_ts = load("data/control")

    cross_matches(cpu_full, cpu_ts, ctl_full, ctl_ts, "full-frame")
    cross_matches(cpu_rc, cpu_ts, ctl_rc, ctl_ts, "render-check crop")

    within_run_matches(cpu_full, cpu_ts, "cpu, full-frame")
    within_run_matches(ctl_full, ctl_ts, "control, full-frame")


if __name__ == "__main__":
    main()
