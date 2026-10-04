#!/usr/bin/env python3
"""The #185 go/no-go: every way a candidate image is worse than the X baseline.

Rules and input shapes: verdict_test.py's header. An empty list is go. A candidate run's
stall_rate is a float (exact) or {"lower_rate", "upper_rate"} (bounded); an exact run is judged
as the bound [x, x].
"""


def regression_reasons(baseline_runs, candidate_runs, baseline_soak, candidate_soak):
    r = []

    def col(runs, k):
        return [x[k] for x in runs]

    b = max(col(baseline_runs, "stall_rate"))
    bounds = [(s["lower_rate"], s["upper_rate"]) if isinstance(s, dict) else (s, s)
              for s in col(candidate_runs, "stall_rate")]
    lo, hi = max(x for x, _ in bounds), max(y for _, y in bounds)
    if lo > b:
        r.append(f"stall rate: candidate worst {lo} > baseline max {b}")
    elif hi > b:
        r.append(f"stall rate: candidate worst {lo}-{hi} straddles baseline max {b}, "
                 f"judged on upper bound")
    b, c = min(col(baseline_runs, "pct_under_50")), min(col(candidate_runs, "pct_under_50"))
    if c < b:
        r.append(f"% frames <50 ms: candidate worst {c} < baseline min {b}")
    b, c = min(col(baseline_runs, "fps")), min(col(candidate_runs, "fps"))
    if c < b:
        r.append(f"mean fps: candidate worst {c} < baseline min {b}")
    for k, what in (("fmax", "module faults simultaneous (fmax)"),
                    ("fever", "module faults ever-seen (fever)"),
                    ("restarts", "kiosk restarts"), ("reboots", "reboots")):
        if candidate_soak[k] > baseline_soak[k]:
            r.append(f"{what}: candidate {candidate_soak[k]} > baseline {baseline_soak[k]}")
    if candidate_soak["memory_problem"]:
        r.append("memory problem signal in the candidate soak")
    return r
