#!/usr/bin/env python3
"""reclassify_cards_window.py <run.txt> [min_live] [steady_from]

Re-judges an S4 smoothness/soak run's CP| samples using only the ones inside p7_min's own
measured window (t >= steady_from seconds since load -- parse_smoothness.py's own
steady_from=15.0, the same warm-up p7 excludes from its stall-rate numbers). The page's
cards-probe.js samples once right at the load event, before the framework has painted any
[data-pwt-card] -- that sample legitimately reads c=0 l=0 and is not evidence of anything
dropping, but the original run-time gate (every sample, no matter how early) VOIDs on it.

Appends a new block to the SAME file -- never overwrites or removes the original VOID/LIVE
line -- reporting: every excluded (t < steady_from) sample's c/l, and the reclassified verdict
(parse_cards_probe.all_at_least) over the judged (t >= steady_from) samples only.
"""
import re
import sys
import os

sys.path.insert(0, "/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation")
import parse_cards_probe as pcp

PAT = re.compile(r"CP\|t=(\d+)\|c=(\d+)\|l=(\d+)")


def main(path, min_live=3, steady_from=15.0):
    min_live = int(min_live)
    steady_from = float(steady_from)
    lines = open(path).read().splitlines()
    excluded, judged = [], []
    for line in lines:
        m = PAT.search(line)
        if not m:
            continue
        t, c, l = int(m.group(1)), int(m.group(2)), int(m.group(3))
        (excluded if t < steady_from else judged).append((t, c, l, line))

    with open(path, "a") as f:
        f.write(f"\n# --- reclassification (t>={steady_from}s window, min_live={min_live}) ---\n")
        if excluded:
            f.write(f"# excluded (t<{steady_from}s) samples: " +
                    ", ".join(f"t={t} c={c} l={l}" for t, c, l, _ in excluded) + "\n")
        else:
            f.write(f"# excluded (t<{steady_from}s) samples: none\n")
        judged_cp_lines = [line for _, _, _, line in judged]
        if not judged_cp_lines:
            f.write("# reclassified verdict: VOID -- no CP| samples inside the measured window\n")
        else:
            try:
                live = pcp.all_at_least(judged_cp_lines, min_live)
                frac = pcp.live_fraction(judged_cp_lines)
            except ValueError as e:
                f.write(f"# reclassified verdict: VOID -- {e}\n")
            else:
                verdict = f"LIVE (l>={min_live} throughout the measured window)" if live else \
                          f"VOID (l<{min_live} at some point inside the measured window)"
                f.write(f"# reclassified verdict: {verdict}, live_fraction(l=4)={frac:.3f} "
                        f"({len(judged_cp_lines)} judged samples, {len(excluded)} excluded)\n")
    print(f"{os.path.basename(path)}: {len(excluded)} excluded, {len(judged)} judged -- see file for verdict")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    main(*sys.argv[1:])
