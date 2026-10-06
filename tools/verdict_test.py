#!/usr/bin/env python3
"""Tests for verdict.regression_reasons, the #185 soak go/no-go.

Contract (function names/shapes are this suite's own design, not a cross-process
boundary -- only verdict.py and this test need to agree on it):

    regression_reasons(baseline_soak, candidate_soak) -> list[str]

  baseline_soak, candidate_soak: each a dict {"fmax": int, "fever": int, "restarts":
  int, "reboots": int, "memory_problem": bool} -- one 1h soak per image (#185 plan:
  1h/config).

  regression_reasons returns a list of human-readable reason strings; [] means go
  (no regression).

Ported from the old 185-wpe-platform-feasibility tip (9c41db2), amended (team-lead,
2026-10-06, relayed by impl): the smoothness half of the original contract -- the
baseline_runs/candidate_runs stall_rate/pct_under_50/fps comparison, the bounded-
stall-rate range rule ("E1"), and the separate flags() straddle-reporting function
("F1") -- is DROPPED entirely. That display-side comparison is superseded by
kiosk-framepace-verdict.py, this branch's own new instrument (tools/kiosk-framepace-
verdict-test.py). Only the soak comparison below survives the port, with the SAME
reason strings the old suite checked for (substring, not exact text, same as
before).

Rules encoded (#185 plan "Verdict", owner rulings 2026-10-04), unchanged by this
amendment:
  - module fault: regression iff candidate_soak.fmax > baseline_soak.fmax
                     OR candidate_soak.fever > baseline_soak.fever
    ("u"/"umax" are recorded, not judged -- no verdict input reads them.)
  - restarts/reboots: regression iff candidate_soak.{restarts,reboots} > baseline_
    soak.{restarts,reboots}
  - memory: regression iff candidate_soak.memory_problem is True -- ABSOLUTE, not
    compared against baseline_soak.memory_problem ("any memory problem signal",
    plan's Verdict section).

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


def soak(fmax, fever, restarts=0, reboots=0, memory_problem=False):
    return {"fmax": fmax, "fever": fever, "restarts": restarts, "reboots": reboots,
            "memory_problem": memory_problem}


BASE_SOAK = soak(fmax=1, fever=2, restarts=0, reboots=0, memory_problem=False)


def test_identical_candidate_is_go():
    reasons = v.regression_reasons(BASE_SOAK, BASE_SOAK)
    check("identical baseline/candidate -> go (no reasons)", reasons == [], detail=str(reasons))


def test_higher_fmax_is_a_regression():
    cand_soak = soak(fmax=2, fever=2)  # 2 > baseline's 1
    reasons = v.regression_reasons(BASE_SOAK, cand_soak)
    check("higher fmax flagged", any("fmax" in r.lower() or "simultaneous" in r.lower()
                                      for r in reasons), detail=str(reasons))


def test_higher_fever_is_a_regression():
    cand_soak = soak(fmax=1, fever=3)  # 3 > baseline's 2
    reasons = v.regression_reasons(BASE_SOAK, cand_soak)
    check("higher fever flagged", any("fever" in r.lower() or "ever-seen" in r.lower()
                                       for r in reasons), detail=str(reasons))


def test_equal_fmax_and_fever_is_not_a_regression():
    cand_soak = soak(fmax=1, fever=2)  # equal to baseline, not worse
    reasons = v.regression_reasons(BASE_SOAK, cand_soak)
    check("equal fmax/fever not flagged",
          not any("fmax" in r.lower() or "fever" in r.lower() for r in reasons),
          detail=str(reasons))


def test_more_restarts_is_a_regression():
    cand_soak = soak(fmax=1, fever=2, restarts=1)
    reasons = v.regression_reasons(BASE_SOAK, cand_soak)
    check("more restarts flagged", any("restart" in r.lower() for r in reasons),
          detail=str(reasons))


def test_more_reboots_is_a_regression():
    cand_soak = soak(fmax=1, fever=2, reboots=1)
    reasons = v.regression_reasons(BASE_SOAK, cand_soak)
    check("more reboots flagged", any("reboot" in r.lower() for r in reasons),
          detail=str(reasons))


def test_any_memory_problem_is_a_regression_even_if_baseline_also_has_one():
    # "any memory problem signal" is absolute, not compared to the baseline's own flag.
    base_soak_with_problem = soak(fmax=1, fever=2, memory_problem=True)
    cand_soak = soak(fmax=1, fever=2, memory_problem=True)
    reasons = v.regression_reasons(base_soak_with_problem, cand_soak)
    check("candidate memory_problem flagged regardless of baseline's own flag",
          any("memory" in r.lower() or "oom" in r.lower() for r in reasons), detail=str(reasons))


def test_no_memory_problem_is_not_a_regression():
    reasons = v.regression_reasons(BASE_SOAK, BASE_SOAK)
    check("no memory_problem not flagged",
          not any("memory" in r.lower() or "oom" in r.lower() for r in reasons),
          detail=str(reasons))


if __name__ == "__main__":
    test_identical_candidate_is_go()
    test_higher_fmax_is_a_regression()
    test_higher_fever_is_a_regression()
    test_equal_fmax_and_fever_is_not_a_regression()
    test_more_restarts_is_a_regression()
    test_more_reboots_is_a_regression()
    test_any_memory_problem_is_a_regression_even_if_baseline_also_has_one()
    test_no_memory_problem_is_not_a_regression()
    print()
    if fails:
        raise SystemExit(f"{fails} check(s) FAILED")
    print("all checks passed")
