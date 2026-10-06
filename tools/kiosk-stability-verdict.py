#!/usr/bin/env python3
"""Stability verdict for one soak against the zero baseline.

    tools/kiosk-stability-verdict.py <capture> <restarts> <reboots> <oom-lines> [<window>]

<capture>: a soak capture holding soak-cards-probe.js's MF| lines. <restarts>,
<reboots>, <oom-lines>: counts over the soak. <window>: the soak's length in seconds,
default 3600.

parse_module_fault.soak_summary gives fmax and fever; verdict.regression_reasons judges
them, the restarts, the reboots and a memory problem (any OOM-killer line) against a
soak with none of these, with identical smoothness runs on both sides so only the soak
rules apply. Prints each reason or why it could not tell, then "regression
reasons=<n>", and exits 0 (no regression), 1 (regression) or 2 (could not tell: fewer
MF| samples than 90 % of one per 30 s over the window, or the last one more than 60 s
short of the window's end).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parse_module_fault  # noqa: E402
import verdict  # noqa: E402

WINDOW = 3600.0
SAMPLE_INTERVAL = 30.0
END_MARGIN = 60.0

ZERO_SOAK = {"fmax": 0, "fever": 0, "restarts": 0, "reboots": 0, "memory_problem": False}
NEUTRAL_RUNS = [{"stall_rate": {"lower_rate": 0.0, "upper_rate": 0.0, "bounded": False},
                 "pct_under_50": 100.0, "fps": 60.0}]


def stability_verdict(mf_lines, restarts, reboots, oom_lines, window=WINDOW,
                      sample_interval=SAMPLE_INTERVAL):
    """{"rc": 0|1|2, "reasons": [...]}; on rc 2 the reasons say why it could not tell."""
    try:
        summary = parse_module_fault.soak_summary(mf_lines)
    except ValueError as e:
        return {"rc": 2, "reasons": [str(e)]}
    samples = [d for d in map(parse_module_fault.parse, mf_lines) if d]
    floor = 0.9 * (window // sample_interval)
    if len(samples) < floor:
        return {"rc": 2, "reasons": [f"{len(samples)} MF| samples, under 90 % of the "
                                     f"{window:g} s window's {window // sample_interval:g}"]}
    last = max(d["t"] for d in samples)
    if last < window - END_MARGIN:
        return {"rc": 2, "reasons": [f"last MF| sample at t={last}, more than "
                                     f"{END_MARGIN:g} s short of the {window:g} s window"]}
    candidate = {"fmax": summary["fmax"], "fever": summary["fever"], "restarts": restarts,
                 "reboots": reboots, "memory_problem": oom_lines > 0}
    reasons = verdict.regression_reasons(NEUTRAL_RUNS, NEUTRAL_RUNS, ZERO_SOAK, candidate)
    return {"rc": 1 if reasons else 0, "reasons": reasons}


def main(argv):
    if len(argv) not in (5, 6):
        print("usage: kiosk-stability-verdict.py <capture> <restarts> <reboots> <oom-lines>"
              " [<window>]", file=sys.stderr)
        print("regression reasons=0")
        return 2
    try:
        lines = Path(argv[1]).read_text().splitlines()
        restarts, reboots, oom_lines = (int(x) for x in argv[2:5])
        window = float(argv[5]) if len(argv) > 5 else WINDOW
    except (OSError, ValueError) as e:
        print(f"kiosk-stability-verdict: {e}", file=sys.stderr)
        print("regression reasons=0")
        return 2
    result = stability_verdict(lines, restarts, reboots, oom_lines, window)
    for reason in result["reasons"]:
        print(("could not tell: " if result["rc"] == 2 else "") + reason)
    print(f"regression reasons={len(result['reasons']) if result['rc'] == 1 else 0}")
    return result["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
