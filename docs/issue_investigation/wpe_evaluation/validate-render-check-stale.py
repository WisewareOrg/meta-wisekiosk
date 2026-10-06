#!/usr/bin/env python3
"""validate-render-check-stale.py <dataset-label> <burst-dir-1> [<burst-dir-2> ...]

Offline validation of tools/kiosk-render-check-stale.py (185-wpe-evaluation 51944db) against
burst data already captured by run-burst-capture-v3*.sh / run-v3-short.sh (15 frames each,
report.txt with "FRAME NNN: fb_before=X fb_after=Y copy_ms=Z" lines). For each burst dir with a
full 15/15 frames (a short burst is skipped, not fed to the helper as malformed data), builds
the helper's manifest ("fb_before= fb_after= ppm=" per line, chronological) and runs it,
recording rc and stale-tile count. Alongside, runs analyze_burst_v3.py on the SAME single burst
dir to read its own disagreeing_excl_late_change count for comparison. No device access.
"""
import re
import subprocess
import sys
import os

FRAMES_EXPECTED = 15
STALE_SCRIPT = "/home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check-stale.py"
HERE = os.path.dirname(os.path.abspath(__file__))
V3_SCRIPT = os.path.join(HERE, "analyze_burst_v3.py")
REPORT_RE = re.compile(r"fb_before=(\d+)\s+fb_after=(\d+)\s+copy_ms=(\d+)")


def report_lines(burst_dir):
    reports = {}
    path = os.path.join(burst_dir, "report.txt")
    if not os.path.exists(path):
        return reports
    with open(path) as f:
        for line in f:
            m = re.match(r"FRAME (\d+): (.*)", line.strip())
            if m:
                reports[int(m.group(1))] = m.group(2)
    return reports


def build_manifest(burst_dir, manifest_path):
    """Returns frames_found, or None if the burst is short (skip, don't feed to the helper)."""
    reports = report_lines(burst_dir)
    lines = []
    frames_found = 0
    for idx in range(1, FRAMES_EXPECTED + 1):
        ppm = os.path.join(burst_dir, f"frame_{idx:03d}.ppm")
        if not os.path.exists(ppm):
            continue
        frames_found += 1
        m = REPORT_RE.search(reports.get(idx, ""))
        if not m:
            continue
        lines.append(f"fb_before={m.group(1)} fb_after={m.group(2)} ppm={os.path.abspath(ppm)}")
    if frames_found < FRAMES_EXPECTED:
        return frames_found, None
    with open(manifest_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return frames_found, len(lines)


def run_stale_helper(manifest_path):
    p = subprocess.run(["python3", STALE_SCRIPT, manifest_path], capture_output=True, text=True)
    m = re.search(r"stale tiles=(\d+)", p.stdout)
    return p.returncode, (int(m.group(1)) if m else None)


def run_v3_single(burst_dir):
    p = subprocess.run(["python3", V3_SCRIPT, "single", burst_dir], capture_output=True, text=True)
    m = re.search(r"disagreeing_excl_late_change=(\d+)", p.stdout)
    if m:
        return int(m.group(1))
    if "VOID" in p.stdout:
        return "VOID"
    return None


def main(label, burst_dirs):
    print(f"=== dataset {label}: {len(burst_dirs)} burst dir(s) ===")
    rc_tally = {}
    for bd in sorted(burst_dirs):
        manifest = "/tmp/render-check-stale-manifest.txt"
        frames_found, n_lines = build_manifest(bd, manifest)
        if n_lines is None:
            print(f"  {bd}: SKIPPED (frames_found={frames_found}/{FRAMES_EXPECTED}, short burst)")
            continue
        rc, stale_tiles = run_stale_helper(manifest)
        v3_count = run_v3_single(bd)
        rc_tally[rc] = rc_tally.get(rc, 0) + 1
        print(f"  {bd}: helper rc={rc} stale_tiles={stale_tiles}  "
              f"v3_disagreeing_excl_late={v3_count}")
    print(f"-- {label} rc tally: {dict(sorted(rc_tally.items()))}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2:])
