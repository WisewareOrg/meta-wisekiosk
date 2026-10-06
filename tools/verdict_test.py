#!/usr/bin/env python3
"""Tests for verdict.regression_reasons and verdict.flags, the #185 go/no-go and its
descriptive flags. code-monkey keeps this suite green without modifying it.

Contract (function names/shapes are this suite's own design, not a cross-process boundary --
only verdict.py and this test need to agree on it):

    regression_reasons(baseline_runs, candidate_runs, baseline_soak, candidate_soak) -> list[str]
    flags(baseline_runs, candidate_runs, baseline_soak, candidate_soak) -> list[str]

  baseline_runs, candidate_runs: each a list of 3 dicts {"stall_rate": {...}, "pct_under_50":
    float, "fps": float} -- one per smoothness run (#185 plan: 3 runs/image). EVERY run's
    "stall_rate" is {"lower_rate": float, "upper_rate": float, "bounded": bool} -- an exact run
    has lower_rate == upper_rate and bounded=False; a bounded run (parse_smoothness.
    steady_stall_bounds, "E2") has lower_rate < upper_rate and bounded=True. Baseline runs may
    be bounded too ("E1" below) -- this is a uniform shape, not float-or-dict.

    "F2" (rev-content finding, orchestrator ruling 2026-10-04): these keys are named
    lower_rate/upper_rate, DISTINCT from steady_stall_bounds' own lower/upper, which are raw
    COUNTS, not rates -- the verdict must consume rates (count / (sec - 15)), never the bare
    counts, because two runs can share a count while differing in rate (different window
    lengths). test_rate_not_count_drives_the_verdict below is the case that would pass on
    counts and fail on rates if the wiring used the wrong one.

  baseline_soak, candidate_soak: each a dict {"fmax": int, "fever": int, "restarts": int,
    "reboots": int, "memory_problem": bool} -- one 1h soak per image (#185 plan: 1h/config).

  regression_reasons returns a list of human-readable reason strings; [] means go (no
  regression) -- UNCHANGED by this suite's revision.

  flags (new, "F1", rev-content finding, orchestrator ruling 2026-10-04): a SEPARATE list of
  descriptive strings, not go/no-go -- a straddle that resolves CLEAR still gets a flag (the
  bound was genuinely ambiguous even though the call came out clean), containing both
  "straddle" and "clear"; a straddle that resolves as a REGRESSION gets a flag containing
  "judged on upper bound" (regression_reasons' own phrase for that case). A DEFINITE regression
  (CL > BU) or a DEFINITE clear (CU <= BL) is not a straddle at all, so flags() carries no
  "straddle" entry for either.

Rules encoded (#185 plan "Verdict" / "Range rule", owner rulings 2026-10-04):
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

  STALL RATE -- "E1" (rev-content finding, orchestrator ruling 2026-10-04): a baseline run can
  be bounded too, so the comparison is bound-vs-bound, not bound-vs-a-single-baseline-float.
    BL = max over baseline_runs of stall_rate.lower_rate   (an exact run contributes its [x, x])
    BU = max over baseline_runs of stall_rate.upper_rate
    CL = max over candidate_runs of stall_rate.lower_rate  (the candidate's worst run's floor)
    CU = max over candidate_runs of stall_rate.upper_rate  (the candidate's worst run's ceiling)
  Then:
    - CL > BU  -> a DEFINITE regression (even the candidate's floor exceeds the baseline's
      own ceiling). Must NOT carry the "judged on upper bound" phrase (reserved below).
    - CU <= BL -> definitely NOT a regression (even the candidate's ceiling is within the
      baseline's own floor).
    - otherwise (straddle) -> judge on the upper rates: regression iff CU > BU, flagged
      "judged on upper bound" (the ruling's own words) when it is.
  With an all-exact baseline (BL == BU == a single B), this reduces to the plain range rule:
  CL > B definite, CU <= B clear, else straddle on CU > B -- i.e. CU > B either way, so it is
  simply "CU > B -> regression" once BL == BU, same outcome as the pre-E1 rule.
  A MIXED candidate set (some runs exact, some bounded) is exercised directly: an exact run's
  [x, x] must feed both CL and CU like any other run's lower_rate/upper_rate would (rev-content
  finding).

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


def stall(lower_rate, upper_rate=None):
    """A run's stall_rate entry. upper_rate=None -> an exact run: lower_rate==upper_rate,
    bounded=False."""
    if upper_rate is None:
        return {"lower_rate": lower_rate, "upper_rate": lower_rate, "bounded": False}
    return {"lower_rate": lower_rate, "upper_rate": upper_rate, "bounded": True}


def runs(stall_rates, pcts, fpses):
    """stall_rates: a list of plain floats (wrapped as exact via stall()) or already-built
    stall() dicts, freely mixed -- a mixed list is itself a test case (see E1 above)."""
    return [{"stall_rate": s if isinstance(s, dict) else stall(s),
             "pct_under_50": p, "fps": f}
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


def test_bounded_stall_rate_clear_regression_when_even_the_floor_exceeds_baseline():
    # baseline max stall_rate is 0.02; lower_rate=0.03 already exceeds it -> definite
    # regression, NOT the "judged on upper bound" case (reserved for the straddle case).
    cand = runs([stall(0.03, 0.05)] * 3, [99.0] * 3, [59.0] * 3)
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("bounded, lower_rate > baseline max -> stall regression flagged",
          any("stall" in r.lower() for r in reasons), detail=str(reasons))
    check("bounded, lower_rate > baseline max -> NOT flagged as judged-on-upper-bound",
          not any("judged on upper bound" in r.lower() for r in reasons), detail=str(reasons))


def test_bounded_stall_rate_clear_pass_when_even_the_ceiling_is_within_baseline():
    # baseline max stall_rate is 0.02; upper_rate=0.015 never reaches it -> definitely not a
    # regression, regardless of what the true value within [0.005, 0.015] turns out to be.
    cand = runs([stall(0.005, 0.015)] * 3, [99.0] * 3, [59.0] * 3)
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("bounded, upper_rate <= baseline max -> no stall regression",
          not any("stall" in r.lower() for r in reasons), detail=str(reasons))


def test_bounded_stall_rate_straddle_is_judged_on_upper_bound():
    # baseline max stall_rate is 0.02; lower_rate=0.015 <= 0.02 < upper_rate=0.025 -- straddles
    # the bound. The ruling: judge on the upper rate (so it IS a regression) and flag it as
    # "judged on upper bound", distinguishing it from the definite-regression case.
    cand = runs([stall(0.015, 0.025)] * 3, [99.0] * 3, [59.0] * 3)
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("straddle -> flagged as a regression", any("stall" in r.lower() for r in reasons),
          detail=str(reasons))
    check("straddle -> flagged 'judged on upper bound'",
          any("judged on upper bound" in r.lower() for r in reasons), detail=str(reasons))


# --- "E1" bounded-baseline fixture: BL = max(0.01, 0.015, 0.02) = 0.02;
# BU = max(0.01, 0.025, 0.02) = 0.025. One baseline run is itself bounded.
E1_BASE = runs([0.01, stall(0.015, 0.025), 0.02], [99.0, 98.5, 99.2], [59.0, 58.5, 59.2])


def test_bounded_baseline_definite_regression_when_candidate_floor_exceeds_baseline_ceiling():
    # CL = CU = 0.03 > BU = 0.025 -> definite regression, not flagged "judged on upper bound".
    cand = runs([0.03] * 3, [99.0] * 3, [59.0] * 3)
    reasons = v.regression_reasons(E1_BASE, cand, BASE_SOAK, BASE_SOAK)
    check("CL > BU -> stall regression flagged", any("stall" in r.lower() for r in reasons),
          detail=str(reasons))
    check("CL > BU -> NOT flagged as judged-on-upper-bound",
          not any("judged on upper bound" in r.lower() for r in reasons), detail=str(reasons))


def test_bounded_baseline_clear_when_candidate_ceiling_within_baseline_floor():
    # CL = CU = 0.015 <= BL = 0.02 -> definitely not a regression.
    cand = runs([0.015] * 3, [99.0] * 3, [59.0] * 3)
    reasons = v.regression_reasons(E1_BASE, cand, BASE_SOAK, BASE_SOAK)
    check("CU <= BL -> no stall regression", not any("stall" in r.lower() for r in reasons),
          detail=str(reasons))


def test_bounded_baseline_straddle_regression_when_candidate_ceiling_exceeds_baseline_ceiling():
    # CL = 0.022 <= BU = 0.025 (not the definite case); CU = 0.03 > BU = 0.025 -> straddle,
    # judged on upper -> regression, flagged.
    cand = runs([stall(0.022, 0.03)] * 3, [99.0] * 3, [59.0] * 3)
    reasons = v.regression_reasons(E1_BASE, cand, BASE_SOAK, BASE_SOAK)
    check("straddle, CU > BU -> stall regression flagged",
          any("stall" in r.lower() for r in reasons), detail=str(reasons))
    check("straddle, CU > BU -> flagged 'judged on upper bound'",
          any("judged on upper bound" in r.lower() for r in reasons), detail=str(reasons))


def test_bounded_baseline_straddle_clear_when_candidate_ceiling_within_baseline_ceiling():
    # CL = 0.021 <= BU = 0.025 (not definite); CU = 0.023; CU <= BL(0.02)? No (not the clear
    # case either) -- falls to the straddle branch: CU(0.023) <= BU(0.025) -> clear.
    cand = runs([stall(0.021, 0.023)] * 3, [99.0] * 3, [59.0] * 3)
    reasons = v.regression_reasons(E1_BASE, cand, BASE_SOAK, BASE_SOAK)
    check("straddle, CU <= BU -> no stall regression",
          not any("stall" in r.lower() for r in reasons), detail=str(reasons))


def test_mixed_candidate_set_exact_run_feeds_both_lower_and_upper():
    # rev-content finding: a candidate set mixing an exact run ([x, x]) with others must have
    # the exact run's x feed BOTH CL and CU, same as any bounded run's bounds would.
    # Against the plain BASE_RUNS (BL=BU=0.02): CL = max(0.03, 0.01, 0.005) = 0.03,
    # CU = max(0.03, 0.02, 0.005) = 0.03. CL(0.03) > BU(0.02) -> definite regression, and it
    # must come from the EXACT run (0.03), not from the bounded run's own upper_rate (0.02,
    # which alone would not exceed baseline).
    cand = runs([0.03, stall(0.01, 0.02), 0.005], [99.0, 98.5, 99.2], [59.0, 58.5, 59.2])
    reasons = v.regression_reasons(BASE_RUNS, cand, BASE_SOAK, BASE_SOAK)
    check("mixed set: exact run's value drives a definite regression",
          any("stall" in r.lower() for r in reasons), detail=str(reasons))
    check("mixed set: NOT flagged as judged-on-upper-bound (the exact run alone decides it)",
          not any("judged on upper bound" in r.lower() for r in reasons), detail=str(reasons))


def test_rate_not_count_drives_the_verdict():
    # "F2": steady_stall_bounds reports COUNTS under "lower"/"upper"; the verdict must consume
    # RATES under "lower_rate"/"upper_rate" (count / (sec - 15)) -- never the bare counts.
    # Two runs with the SAME count (10 stalls each) but different window lengths have
    # DIFFERENT rates: baseline's window is 200s (rate = 10/185 = 0.05405...), candidate's is
    # 100s (rate = 10/85 = 0.11765...). By count they read identical (10 == 10, no
    # regression); by rate the candidate is more than double the baseline's -- a regression.
    # A verdict wired to the counts instead of the rates would pass this fixture; only the
    # correct rate-based wiring flags it.
    baseline_count, baseline_window = 10, 200
    candidate_count, candidate_window = 10, 100
    baseline_rate = baseline_count / (baseline_window - 15)
    candidate_rate = candidate_count / (candidate_window - 15)
    assert baseline_rate != candidate_rate, "fixture must have genuinely different rates"
    base = runs([baseline_rate] * 3, [99.0] * 3, [59.0] * 3)
    cand = runs([candidate_rate] * 3, [99.0] * 3, [59.0] * 3)
    reasons = v.regression_reasons(base, cand, BASE_SOAK, BASE_SOAK)
    check("same stall COUNT (10 == 10), different window length -> rate-based regression "
          "flagged (0.1176 > 0.0541)",
          any("stall" in r.lower() for r in reasons), detail=str(reasons))


# --- "F1": verdict.flags, a separate, non-go/no-go, descriptive list -------

def test_flags_straddle_clear_carries_both_straddle_and_clear():
    cand = runs([stall(0.021, 0.023)] * 3, [99.0] * 3, [59.0] * 3)
    flags = v.flags(E1_BASE, cand, BASE_SOAK, BASE_SOAK)
    check("straddle-clear: a flag mentions both 'straddle' and 'clear'",
          any("straddle" in f.lower() and "clear" in f.lower() for f in flags),
          detail=str(flags))


def test_flags_straddle_regression_carries_judged_on_upper_bound():
    cand = runs([stall(0.022, 0.03)] * 3, [99.0] * 3, [59.0] * 3)
    flags = v.flags(E1_BASE, cand, BASE_SOAK, BASE_SOAK)
    check("straddle-regression: a flag contains 'judged on upper bound'",
          any("judged on upper bound" in f.lower() for f in flags), detail=str(flags))


def test_flags_definite_regression_has_no_straddle_flag():
    cand = runs([0.03] * 3, [99.0] * 3, [59.0] * 3)  # CL=CU=0.03 > BU=0.025, definite
    flags = v.flags(E1_BASE, cand, BASE_SOAK, BASE_SOAK)
    check("definite regression: no flag mentions 'straddle'",
          not any("straddle" in f.lower() for f in flags), detail=str(flags))


def test_flags_definite_clear_has_no_straddle_flag():
    cand = runs([0.015] * 3, [99.0] * 3, [59.0] * 3)  # CL=CU=0.015 <= BL=0.02, definite
    flags = v.flags(E1_BASE, cand, BASE_SOAK, BASE_SOAK)
    check("definite clear: no flag mentions 'straddle'",
          not any("straddle" in f.lower() for f in flags), detail=str(flags))


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
    test_bounded_baseline_definite_regression_when_candidate_floor_exceeds_baseline_ceiling()
    test_bounded_baseline_clear_when_candidate_ceiling_within_baseline_floor()
    test_bounded_baseline_straddle_regression_when_candidate_ceiling_exceeds_baseline_ceiling()
    test_bounded_baseline_straddle_clear_when_candidate_ceiling_within_baseline_ceiling()
    test_mixed_candidate_set_exact_run_feeds_both_lower_and_upper()
    test_rate_not_count_drives_the_verdict()
    test_flags_straddle_clear_carries_both_straddle_and_clear()
    test_flags_straddle_regression_carries_judged_on_upper_bound()
    test_flags_definite_regression_has_no_straddle_flag()
    test_flags_definite_clear_has_no_straddle_flag()
    print()
    if fails:
        raise SystemExit(f"{fails} check(s) FAILED")
    print("all checks passed")
