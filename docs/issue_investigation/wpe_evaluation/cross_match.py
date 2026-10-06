#!/usr/bin/env python3
"""cross_match.py -- offline, no visual inspection. For every revert frame found by
analyze_burst2.py's rule (hash[i]==hash[i-2], hash[i-1] differs), using both the render-check
crop and each of the three hand-picked crops from analyze_burst.py, report:
  - every earlier index (within the same run) whose crop-hash equals this frame's (full
    provenance, not just i-2)
  - for CPU-run revert frames only: every CONTROL-run frame index whose crop-hash matches,
    byte-for-byte, for that same crop definition
All comparisons are sha256 of raw cropped pixel bytes -- no image is opened by eye.
"""
import sys, hashlib, glob, os

sys.path.insert(0, os.path.dirname(__file__))
from analyze_burst import read_ppm, crop as crop_fn

CROPS = {
    "rendercheck": (560, 300, 220, 20),
    "clock": (380, 120, 50, 45),
    "weather": (270, 90, 955, 45),
    "parkwait": (50, 130, 360, 295),
}


def load_hashes(run_dir):
    frames = sorted(glob.glob(os.path.join(run_dir, "frame_*.ppm")))
    ts_path = os.path.join(run_dir, "timestamps.txt")
    with open(ts_path) as f:
        timestamps = [float(l.strip()) for l in f if l.strip()]
    per_crop = {name: [] for name in CROPS}
    for fp in frames:
        w, h, data = read_ppm(fp)
        for name, (cw, ch, cx, cy) in CROPS.items():
            c = crop_fn(w, h, data, cw, ch, cx, cy)
            per_crop[name].append(hashlib.sha256(c).hexdigest())
    return per_crop, timestamps, len(frames)


def reverts_for(hashes):
    out = []
    for i in range(2, len(hashes)):
        if hashes[i] == hashes[i - 2] and hashes[i - 1] != hashes[i]:
            out.append(i)
    return out


def main():
    control_hashes, control_ts, n_control = load_hashes("data/control")
    cpu_hashes, cpu_ts, n_cpu = load_hashes("data/cpu")

    for cropname in CROPS:
        print(f"=== crop={cropname} ===")

        ch = control_hashes[cropname]
        c_reverts = reverts_for(ch)
        print(f"-- control reverts ({len(c_reverts)}): {[i+1 for i in c_reverts]}")
        for i in c_reverts:
            matches = [j for j in range(i) if ch[j] == ch[i]]
            print(f"   frame {i+1} (t={control_ts[i]:.3f}) matches EARLIER control frames (1-based): "
                  f"{[j+1 for j in matches]} at t={[round(control_ts[j],3) for j in matches]}")

        ph = cpu_hashes[cropname]
        p_reverts = reverts_for(ph)
        print(f"-- cpu reverts ({len(p_reverts)}): {[i+1 for i in p_reverts]}")
        for i in p_reverts:
            within = [j for j in range(i) if ph[j] == ph[i]]
            cross = [j for j in range(n_control) if ch[j] == ph[i]]
            print(f"   frame {i+1} (t={cpu_ts[i]:.3f}) matches EARLIER cpu frames (1-based): "
                  f"{[j+1 for j in within]}; matches CONTROL frames (1-based): {[j+1 for j in cross]}"
                  + (f" at control t={[round(control_ts[j],3) for j in cross]}" if cross else ""))
        print()


if __name__ == "__main__":
    main()
