#!/usr/bin/env python3
"""diagnose-stale-series.py <stale-diag-dir> [<fixed-image burst dir> ...]

Why tools/kiosk-render-check-stale.py does or does not call STALE on a kept render-check series,
against the v3 burst taken right after it.

<stale-diag-dir> holds seriesN/ (manifest.txt + the 30 PPMs it names) and seriesN-v3burst/control-1
(a run-burst-capture-v3 burst). Per series:
  (a) the helper's verdict on the full manifest;
  (b) the burst's disagreeing tiles, late-change artifacts excluded (analyze_burst_v3's rule);
  (c) per fb, the stable-capture count, and for each burst-disagreeing tile why the helper did
      not count it: an fb not self-consistent on it across the series (with the worst MAD
      against that fb's first capture), the pair skipped by the per-pair single-split rule or as
      two singletons, an fb with no stable capture, or the two fbs' first captures agreeing;
  (d) the helper on every sliding window of 10 and of 15 consecutive captures.
Each fixed-image burst dir (frame_NNN.ppm + report.txt) is run through the helper whole and in
sliding windows of 10 and 15, for false positives. Markdown on stdout.
"""
import glob
import importlib.util
import os
import re
import sys
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "..", "..", "tools")
sys.path.insert(0, HERE)
import analyze_burst_v3 as v3  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "stale", os.path.join(TOOLS, "kiosk-render-check-stale.py"))
stale = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stale)
LINE = re.compile(r"fb_before=(\d+) fb_after=(\d+) ppm=(\S+)$")
FRAME = re.compile(r"FRAME (\d+): fb_before=(\d+) fb_after=(\d+)")


def manifest_captures(path):
    caps = []
    for line in open(path):
        m = LINE.match(line.strip())
        if m:
            caps.append({"fb_before": int(m.group(1)), "fb_after": int(m.group(2)),
                         "ppm": open(m.group(3), "rb").read()})
    return caps


def burst_captures(d):
    fbs = {}
    for line in open(os.path.join(d, "report.txt")):
        m = FRAME.match(line.strip())
        if m:
            fbs[int(m.group(1))] = (int(m.group(2)), int(m.group(3)))
    caps = []
    for i, fp in enumerate(sorted(glob.glob(os.path.join(d, "frame_*.ppm"))), start=1):
        if i in fbs:
            caps.append({"fb_before": fbs[i][0], "fb_after": fbs[i][1],
                         "ppm": open(fp, "rb").read()})
    return caps


def windows(caps, n):
    return [stale.stale_verdict(caps[i:i + n])["rc"] for i in range(0, len(caps) - n + 1)]


def explain(caps, burst_tiles):
    """Per fb stable counts, and per burst-disagreeing tile the helper's reason."""
    frames = [stale.parse_ppm(c["ppm"]) for c in caps]
    stable = [(c["fb_before"], f[2]) for c, f in zip(caps, frames) if c["fb_before"] == c["fb_after"]]
    ids = [fb for fb, _ in stable]
    groups = {}
    for fb, rgb in stable:
        groups.setdefault(fb, []).append(rgb)
    w = frames[0][0]
    pairs = list(combinations(groups, 2))
    skipped = {p: ("two singletons" if len(groups[p[0]]) < 2 and len(groups[p[1]]) < 2
                   else "single split" if stale.single_split([f for f in ids if f in p]) else None)
               for p in pairs}
    out = {}
    for tx, ty in sorted(burst_tiles):
        t = (tx * 40, ty * 40, min(tx * 40 + 40, w), min(ty * 40 + 40, frames[0][1]))
        if len(groups) < 2:
            out[(tx, ty)] = "only one fb has a stable capture"
            continue
        drift = {fb: max((stale.tile_mad(g[0], o, w, t) for o in g[1:]), default=0.0)
                 for fb, g in groups.items()}
        reasons = []
        for p in pairs:
            if skipped[p]:
                reasons.append(f"pair {p[0]}/{p[1]} skipped ({skipped[p]})")
                continue
            bad = [f"fb {fb} not self-consistent (max MAD {drift[fb]:.2f})"
                   for fb in p if len(groups[fb]) >= 2 and drift[fb] > 1]
            if bad:
                reasons.append(f"pair {p[0]}/{p[1]}: " + "; ".join(bad))
                continue
            d = stale.tile_mad(groups[p[0]][0], groups[p[1]][0], w, t)
            reasons.append(f"pair {p[0]}/{p[1]}: COUNTED (MAD {d:.2f})" if d > 1
                           else f"pair {p[0]}/{p[1]}: first captures agree (MAD {d:.2f})")
        out[(tx, ty)] = " | ".join(reasons)
    return {fb: len(g) for fb, g in groups.items()}, out


def main(argv):
    base, fixed = argv[1], argv[2:]
    print("# STALE helper vs v3 burst, per kept render-check series\n")
    for sd in sorted(glob.glob(os.path.join(base, "series[0-9]*")), key=lambda p: p):
        if sd.endswith("-v3burst"):
            continue
        name = os.path.basename(sd)
        caps = manifest_captures(os.path.join(sd, "manifest.txt"))
        verdict = stale.stale_verdict(caps)
        bd = os.path.join(base, name + "-v3burst", "control-1")
        found, bstable = v3.load_burst(bd)
        _, dis, late = v3.analyze_one_burst(bstable)
        burst = dis - late
        counts, why = explain(caps, burst)
        print(f"## {name}\n")
        print(f"- (a) helper on {len(caps)} captures: rc {verdict['rc']}, "
              f"stale tiles {verdict['stale_tiles']}")
        print(f"- (b) v3 burst ({found} frames, {len(bstable)} stable): {len(dis)} disagreeing, "
              f"{len(burst)} excluding late-change")
        print(f"- (c) stable captures per fb: {counts}")
        tally = {}
        for t, r in why.items():
            key = re.sub(r"\(max MAD [0-9.]+\)|\(MAD [0-9.]+\)", "", r)
            tally[key] = tally.get(key, 0) + 1
        for r, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"    - {n} tile(s): {r.strip()}")
        for n in (10, 15):
            rcs = windows(caps, n)
            print(f"- (d) windows of {n}: rc {rcs} -> {rcs.count(3)}/{len(rcs)} STALE")
        print()
    if fixed:
        print("# Fixed-image bursts through the helper (false positives)\n")
        for d in fixed:
            caps = burst_captures(d)
            v = stale.stale_verdict(caps)
            w10, w15 = windows(caps, 10), windows(caps, 15)
            print(f"- {d}: whole ({len(caps)}) rc {v['rc']}; windows of 10 STALE "
                  f"{w10.count(3)}/{len(w10)}; windows of 15 STALE {w15.count(3)}/{len(w15)}")


if __name__ == "__main__":
    main(sys.argv)
