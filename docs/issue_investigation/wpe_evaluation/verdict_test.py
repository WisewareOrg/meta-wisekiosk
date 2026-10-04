#!/usr/bin/env python3
"""RED tests for verdict.regression_reasons, the #185 go/no-go function.

verdict does not exist yet -- this file is the spec code-monkey makes green.

Contract (function name/shape is this suite's own design, not a cross-process boundary --
only verdict.py and this test need to agree on it):

    regression_reasons(baseline_runs, candidate_runs, baseline_soak, candidate_soak) -> list[str]

  baseline_runs, candidate_runs: each a list of 3 dicts {"stall_rate": float,
    "pct_under_50": float, "fps": float} -- one per smoothness run (#185 plan: 3 runs/image).
  baseline_soak, candidate_soak: each a dict {"fmax": int, "fever": int, "restarts": int,
    "reboots": int, "memory_problem": bool} -- one 1h soak per image (#185 plan: 1h/config).
  Returns a list of human-readable reason strings; [] means go (no regression).

Rules encoded (#185 plan "Verdict" / "Range rule", owner rulings 2026-10-04):
  - stall_rate: regression iff max(candidate) > max(baseline)              [worse = higher]
  - pct_under_50: regression iff min(candidate) < min(baseline)           [worse = lower]
  - fps:         regression iff min(candidate) < min(baseline)            [worse = lower]
  - module fault: regression iff candidate_soak.fmax > baseline_soak.fmax
                     OR candidate_soak.fever > baseline_soak.fever
    ("u"/"umax" are recorded, not judged -- no verdict input reads them.)
  - restarts/reboots: regression iff candidate_soak.{restarts,reboots} > baseline_soak.{..}
  - memory: regression iff candidate_soak.memory_problem is True -- ABSOLUTE, not compared
    against baseline_soak.memory_problem ("any memory problem signal", plan's Verdict section).
  - Degenerate range (baseline's 3 runs identical) applies literally: equal to the baseline
    bound is NOT a regression (strict worse-than only); one tick past it IS.
  - time to page: recorded, not judged -- no verdict input reads it.

  BOUNDED stall rate (orchestrator ruling 2026-10-04, for a run where p7_min.js's bigTotal >
  len(big) -- parse_smoothness.steady_stall_bounds's "bounded" case): a candidate run's
  "stall_rate" entry may be a float (exact) as above, OR a dict {"lower_rate": float,
  "upper_rate": float} (bounded). baseline_runs are always exact floats -- only a candidate
  run can be bounded. Let B = baseline's max exact stall_rate. For a bounded candidate run:
    - lower_rate > B  -> a DEFINITE regression (even the floor exceeds baseline).
    - upper_rate <= B -> definitely NOT a regression (even the ceiling is within baseline).
    - otherwise (lower_rate <= B < upper_rate, "straddle") -> judge on upper_rate: a
      regression, and its reason text must say "judged on upper bound" (the ruling's own
      words) -- this is what distinguishes it from the definite-regression case above, which
      must NOT carry that phrase.
  These three fixtures each replicate one bounded value across all 3 candidate runs, so the
  verdict's 3-way rule is exercised without also needing a rule for mixing bounded and exact
  runs within one candidate set -- that combination is not specified and is not tested here.

Run: python3 verdict_test.py
"""
import verdict as v

fails = 0


def check(name, cond, detail=""):
    global fails
    status = "PASS" if cond else "FAIL"
    if not cond:
        fails += 1
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))


def runs(stall_rates, pcts, fpses):
    return [{"stall_rate": s, "pct_under_50": p, "fps": f}
            for s, p, f in zip(stall_rates, pcts, fpses)]


def soak(fmax, fever, restarts=0, reboots=0, memory_problem=False):
    return {"fmax": fmax, "fever": fever, "restarts": restarts, "reboots": reboots,
            "memory_problem": memory_problem}


BASE_RUNS = runs([0.01, 0.02, 0.015], [99.0, 98.5, 99.2], [59.0, 58.5, 59.2])
BASE_SOAK = soak(fmax=1, fever=2, restarts=0, reboots=0, memory_problem=False)


def test_identical_candidate_is_go():
    reasons = v.regression_reasons(BASE_RUNS, BASE_RUNS, BASE_SOAK, BASE_SOAK)
    check("identical baseline/candidate -> go (no reasons)", reasons == [], detail=str(reasons))


def test_worse_stall_rate_is_a_regression():
    cand = runs([0.01, 0.02, 0.03], [99.0, 98.5, 99.2], [59.0, 58.5, 59.2])  # worst 0.03 > 0.02
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("worse stall rate flagged", any("stall" in r.lower() for r in reasons),
          detail=str(reasons))


def test_better_stall_rate_is_not_a_regression():
    cand = runs([0.005, 0.01, 0.015], [99.0, 98.5, 99.2], [59.0, 58.5, 59.2])  # worst 0.015 < 0.02
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("better stall rate not flagged", not any("stall" in r.lower() for r in reasons),
          detail=str(reasons))


def test_worse_pct_under_50_is_a_regression():
    cand = runs([0.01, 0.02, 0.015], [99.0, 98.5, 95.0], [59.0, 58.5, 59.2])  # worst 95.0 < 98.5
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("worse %<50ms flagged", any("50" in r for r in reasons), detail=str(reasons))


def test_worse_fps_is_a_regression():
    cand = runs([0.01, 0.02, 0.015], [99.0, 98.5, 99.2], [59.0, 50.0, 59.2])  # worst 50.0 < 58.5
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("worse fps flagged", any("fps" in r.lower() for r in reasons), detail=str(reasons))


def test_higher_fmax_is_a_regression():
    cand_soak = soak(fmax=2, fever=2)  # 2 > baseline's 1
    reasons = v.regression_reasons(BASE_RUNS, BASE_RUNS, BASE_SOAK, cand_soak)
    check("higher fmax flagged", any("fmax" in r.lower() or "simultaneous" in r.lower()
                                      for r in reasons), detail=str(reasons))


def test_higher_fever_is_a_regression():
    cand_soak = soak(fmax=1, fever=3)  # 3 > baseline's 2
    reasons = v.regression_reasons(BASE_RUNS, BASE_RUNS, BASE_SOAK, cand_soak)
    check("higher fever flagged", any("fever" in r.lower() or "ever-seen" in r.lower()
                                       for r in reasons), detail=str(reasons))


def test_equal_fmax_and_fever_is_not_a_regression():
    cand_soak = soak(fmax=1, fever=2)  # equal to baseline, not worse
    reasons = v.regression_reasons(BASE_RUNS, BASE_RUNS, BASE_SOAK, cand_soak)
    check("equal fmax/fever not flagged",
          not any("fmax" in r.lower() or "fever" in r.lower() for r in reasons),
          detail=str(reasons))


def test_more_restarts_is_a_regression():
    cand_soak = soak(fmax=1, fever=2, restarts=1)
    reasons = v.regression_reasons(BASE_RUNS, BASE_RUNS, BASE_SOAK, cand_soak)
    check("more restarts flagged", any("restart" in r.lower() for r in reasons),
          detail=str(reasons))


def test_more_reboots_is_a_regression():
    cand_soak = soak(fmax=1, fever=2, reboots=1)
    reasons = v.regression_reasons(BASE_RUNS, BASE_RUNS, BASE_SOAK, cand_soak)
    check("more reboots flagged", any("reboot" in r.lower() for r in reasons),
          detail=str(reasons))


def test_any_memory_problem_is_a_regression_even_if_baseline_also_has_one():
    # "any memory problem signal" is absolute, not compared to the baseline's own flag.
    base_soak_with_problem = soak(fmax=1, fever=2, memory_problem=True)
    cand_soak = soak(fmax=1, fever=2, memory_problem=True)
    reasons = v.regression_reasons(BASE_RUNS, BASE_RUNS, base_soak_with_problem, cand_soak)
    check("candidate memory_problem flagged regardless of baseline's own flag",
          any("memory" in r.lower() or "oom" in r.lower() for r in reasons), detail=str(reasons))


def test_no_memory_problem_is_not_a_regression():
    reasons = v.regression_reasons(BASE_RUNS, BASE_RUNS, BASE_SOAK, BASE_SOAK)
    check("no memory_problem not flagged",
          not any("memory" in r.lower() or "oom" in r.lower() for r in reasons),
          detail=str(reasons))


def test_degenerate_range_equal_is_not_a_regression():
    # Baseline's 3 runs identical -> range is a single point. Candidate exactly matching it
    # is NOT worse -- proves no implicit tolerance band is subtracted from the bound.
    degenerate_base = runs([0.02, 0.02, 0.02], [98.0, 98.0, 98.0], [58.0, 58.0, 58.0])
    cand = runs([0.02, 0.02, 0.02], [98.0, 98.0, 98.0], [58.0, 58.0, 58.0])
    reasons = v.regression_reasons(degenerate_base, cand, BASE_SOAK, BASE_SOAK)
    check("degenerate range, exact match -> go", reasons == [], detail=str(reasons))


def test_degenerate_range_one_tick_worse_is_a_regression():
    # Same degenerate baseline; candidate one tick past it on EVERY axis must all be flagged
    # -- proves the literal bound has no tolerance added either.
    degenerate_base = runs([0.02, 0.02, 0.02], [98.0, 98.0, 98.0], [58.0, 58.0, 58.0])
    cand = runs([0.021, 0.021, 0.021], [97.9, 97.9, 97.9], [57.9, 57.9, 57.9])
    reasons = v.regression_reasons(degenerate_base, cand, BASE_SOAK, BASE_SOAK)
    check("degenerate range, one tick worse on stall rate -> flagged",
          any("stall" in r.lower() for r in reasons), detail=str(reasons))
    check("degenerate range, one tick worse on %<50ms -> flagged",
          any("50" in r for r in reasons), detail=str(reasons))
    check("degenerate range, one tick worse on fps -> flagged",
          any("fps" in r.lower() for r in reasons), detail=str(reasons))


def bounded_runs(lower_rate, upper_rate):
    # Same bounded stall value on all 3 candidate runs -- see module docstring on why.
    return [{"stall_rate": {"lower_rate": lower_rate, "upper_rate": upper_rate},
             "pct_under_50": 99.0, "fps": 59.0} for _ in range(3)]


def test_bounded_stall_rate_clear_regression_when_even_the_floor_exceeds_baseline():
    # baseline max stall_rate is 0.02; lower=0.03 already exceeds it -> definite regression,
    # NOT the "judged on upper bound" case (that phrase is reserved for the straddle case).
    cand = bounded_runs(lower_rate=0.03, upper_rate=0.05)
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("bounded, lower > baseline max -> stall regression flagged",
          any("stall" in r.lower() for r in reasons), detail=str(reasons))
    check("bounded, lower > baseline max -> NOT flagged as judged-on-upper-bound",
          not any("judged on upper bound" in r.lower() for r in reasons), detail=str(reasons))


def test_bounded_stall_rate_clear_pass_when_even_the_ceiling_is_within_baseline():
    # baseline max stall_rate is 0.02; upper=0.015 never reaches it -> definitely not a
    # regression, regardless of what the true value within [0.005, 0.015] turns out to be.
    cand = bounded_runs(lower_rate=0.005, upper_rate=0.015)
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("bounded, upper <= baseline max -> no stall regression",
          not any("stall" in r.lower() for r in reasons), detail=str(reasons))


def test_bounded_stall_rate_straddle_is_judged_on_upper_bound():
    # baseline max stall_rate is 0.02; lower=0.015 <= 0.02 < upper=0.025 -- straddles the
    # bound. The ruling: judge on the upper rate (so it IS a regression) and flag it as
    # "judged on upper bound", distinguishing it from the definite-regression case.
    cand = bounded_runs(lower_rate=0.015, upper_rate=0.025)
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("straddle -> flagged as a regression", any("stall" in r.lower() for r in reasons),
          detail=str(reasons))
    check("straddle -> flagged 'judged on upper bound'",
          any("judged on upper bound" in r.lower() for r in reasons), detail=str(reasons))


if __name__ == "__main__":
    test_identical_candidate_is_go()
    test_worse_stall_rate_is_a_regression()
    test_better_stall_rate_is_not_a_regression()
    test_worse_pct_under_50_is_a_regression()
    test_worse_fps_is_a_regression()
    test_higher_fmax_is_a_regression()
    test_higher_fever_is_a_regression()
    test_equal_fmax_and_fever_is_not_a_regression()
    test_more_restarts_is_a_regression()
    test_more_reboots_is_a_regression()
    test_any_memory_problem_is_a_regression_even_if_baseline_also_has_one()
    test_no_memory_problem_is_not_a_regression()
    test_degenerate_range_equal_is_not_a_regression()
    test_degenerate_range_one_tick_worse_is_a_regression()
    test_bounded_stall_rate_clear_regression_when_even_the_floor_exceeds_baseline()
    test_bounded_stall_rate_clear_pass_when_even_the_ceiling_is_within_baseline()
    test_bounded_stall_rate_straddle_is_judged_on_upper_bound()
    print()
    if fails:
        raise SystemExit(f"{fails} check(s) FAILED")
    print("all checks passed")
