#!/usr/bin/env python3
"""The #185 go/no-go: every way a candidate image is worse than the X baseline.

Rules and input shapes: verdict_test.py's header. An empty list is go. Every run's stall_rate is
{"lower", "upper", "bounded"}; an exact run has lower == upper.
"""


def regression_reasons(baseline_runs, candidate_runs, baseline_soak, candidate_soak):
    r = []

    def col(runs, k):
        return [x[k] for x in runs]

    def worst(runs, end):
        return max(x["stall_rate"][end] for x in runs)

    bl, bu = worst(baseline_runs, "lower"), worst(baseline_runs, "upper")
    cl, cu = worst(candidate_runs, "lower"), worst(candidate_runs, "upper")
    if cl > bu:
        r.append(f"stall rate: candidate worst {cl}-{cu} > baseline max {bl}-{bu}")
    elif cu > bu:
        r.append(f"stall rate: candidate worst {cl}-{cu} straddles baseline max {bl}-{bu}, "
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
