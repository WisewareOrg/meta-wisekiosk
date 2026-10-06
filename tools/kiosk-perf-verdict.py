#!/usr/bin/env python3
"""Smoothness verdict for one capture against the X baseline.

    tools/kiosk-perf-verdict.py <capture> [<baseline.json>] [<min_live>]

<capture>: a kiosk journal capture holding smoothness-cards-probe.js's MP| and CP|
lines. <baseline.json>: {"runs": [...]} in verdict.py's baseline_runs shape, default
kiosk-perf-baseline.json beside this script. <min_live>: the cards gate, default 4.

The capture's last parseable MP| line is the candidate run (parse_smoothness.py);
verdict.regression_reasons judges it against the baseline runs with an identical soak
on both sides, so only the stall-rate, % frames <50 ms and fps rules apply. Every CP|
sample at t >= 15 s must show l >= min_live (parse_cards_probe.all_at_least). Prints
each reason or why it could not tell, then "regression reasons=<n>", and exits 0 (no
regression), 1 (regression) or 2 (could not tell: no MP| payload, no CP| sample in the
judged window, or one under min_live).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import journal_extract  # noqa: E402
import parse_cards_probe  # noqa: E402
import parse_smoothness  # noqa: E402
import verdict  # noqa: E402

STEADY_FROM = 15.0
NEUTRAL_SOAK = {"fmax": 0, "fever": 0, "restarts": 0, "reboots": 0, "memory_problem": False}


def perf_verdict(lines, baseline_runs, min_live=4, steady_from=STEADY_FROM):
    """{"rc": 0|1|2, "reasons": [...]}; on rc 2 the reasons say why it could not tell."""
    d = journal_extract.last_parseable(lines, parse_smoothness.parse)
    if d is None:
        return {"rc": 2, "reasons": ["no MP| payload in the capture"]}

    judged = [line for line in lines
              if (s := parse_cards_probe.parse(line)) and s["t"] >= steady_from]
    if not judged:
        return {"rc": 2, "reasons": [f"no CP| sample at t >= {steady_from} s"]}
    if not parse_cards_probe.all_at_least(judged, min_live):
        return {"rc": 2, "reasons": [f"cards dropped below l={min_live} at t >= {steady_from} s"]}

    b = parse_smoothness.steady_stall_bounds(d, steady_from)
    candidate = {"stall_rate": {"lower_rate": b["lower_rate"], "upper_rate": b["upper_rate"],
                                "bounded": b["bounded"]},
                 "pct_under_50": parse_smoothness.pct_under_50ms(d),
                 "fps": parse_smoothness.mean_fps(d)}
    reasons = verdict.regression_reasons(baseline_runs, [candidate], NEUTRAL_SOAK, NEUTRAL_SOAK)
    return {"rc": 1 if reasons else 0, "reasons": reasons}


def main(argv):
    if not 2 <= len(argv) <= 4:
        print("usage: kiosk-perf-verdict.py <capture> [<baseline.json>] [<min_live>]",
              file=sys.stderr)
        print("regression reasons=0")
        return 2
    try:
        lines = Path(argv[1]).read_text().splitlines()
        baseline_path = Path(argv[2]) if len(argv) > 2 else HERE / "kiosk-perf-baseline.json"
        baseline = json.loads(baseline_path.read_text())["runs"]
        min_live = int(argv[3]) if len(argv) > 3 else 4
    except (OSError, ValueError, KeyError) as e:
        print(f"kiosk-perf-verdict: {e}", file=sys.stderr)
        print("regression reasons=0")
        return 2
    result = perf_verdict(lines, baseline, min_live)
    for reason in result["reasons"]:
        print(("could not tell: " if result["rc"] == 2 else "") + reason)
    print(f"regression reasons={len(result['reasons']) if result['rc'] == 1 else 0}")
    return result["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
