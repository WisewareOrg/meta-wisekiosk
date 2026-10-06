#!/usr/bin/env python3
"""Self-test for kiosk-perf-verdict.py, the one-instrument smoothness check bench runs
and the pipeline both use. Run by hand -- not wired into just guards or ci-guards.sh.

    kiosk-perf-verdict-test.py    -- every case, both directions

THE CONTRACT THIS PINS, since kiosk-perf-verdict.py does not exist yet and this test is
what fixes its shape:

  perf_verdict(lines, baseline_runs, min_live=4, steady_from=15.0,
               capture_length=585.0)
      -> {"rc": 0|1|2, "reasons": [str, ...]}

  lines: a capture's raw text lines, in chronological order, carrying both gpu_
  compositing/p7_min.js's MP| frame-time payloads and cards-probe.js's CP| cards-live
  payloads mixed together, exactly as a real journal capture holds them.

  baseline_runs: a list of 3 dicts {"stall_rate": {"lower_rate", "upper_rate",
  "bounded"}, "pct_under_50", "fps"} -- verdict.py's own baseline_runs shape, loaded by
  the CLI from the committed tools/kiosk-perf-baseline.json (the X baseline's Runs 2-4,
  exactly as the README's "Metrics" tables give them).

  Processing, reusing the moved tools AS THEY ARE, not reimplemented:
  - The capture's LAST parseable MP| line (journal_extract.last_parseable, parse_
    smoothness.parse) gives one candidate run: fps (mean_fps), pct_under_50
    (pct_under_50ms), and stall_rate from steady_stall_bounds(d) -- {"lower_rate",
    "upper_rate", "bounded"}.
  - CP| lines are filtered to the JUDGED window (t >= steady_from, the same 15.0 s
    steady_from parse_smoothness uses) -- run-s4-smoothness.sh's own convention, not
    reimplemented differently here. parse_cards_probe.all_at_least(judged, min_live)
    must hold for every judged sample.
  - The verdict itself is verdict.regression_reasons(baseline_runs, [candidate_run],
    NEUTRAL_SOAK, NEUTRAL_SOAK) -- the SAME baseline/candidate soak dict on both sides
    so no soak-side reason can ever fire, leaving only the smoothness rules (stall
    rate, pct_under_50, fps) live. This reuses regression_reasons whole rather than
    reimplementing half of it; the neutral-soak shape is this test's own design, not
    spec-fixed.

  rc=0: no regression (reasons == []).
  rc=1: regression (reasons is the printed list).
  rc=2 (could not tell), in ANY of these cases:
    - no MP| payload parses in the whole capture;
    - the judged CP| window (t >= steady_from) is empty, or any sample in it has
      l < min_live -- run-s4-smoothness.sh's own cards gate, read as could-not-tell,
      never a pass;
    - the MP| payload's own sec < 0.9 * capture_length (review finding B2: every real
      smoothness capture was 569-583s of a nominal 585s capture -- sec < 526.5
      signals a restart or truncation mid-capture, not a short-but-real run). Checked
      BEFORE computing stall bounds, so a payload ending at or before steady_from
      (sec <= 15) reads rc=2 cleanly, never raising or dividing by the zero/negative
      (sec - steady_from) window that would otherwise follow;
    - ANY OTHER exception raised while judging (review finding B2, refined): the
      length precheck above is this tool's own chosen way to avoid the sec<=15
      ZeroDivisionError, but the actual CONTRACT is broader and implementation-
      agnostic -- perf_verdict must never propagate an exception to its caller.
      Whatever raises while computing the candidate run or the verdict reads
      rc=2, could-not-tell, not a crash. Pinned using the same sec==steady_from
      payload the length check already guards, so the contract holds regardless
      of which internal mechanism (check ordering, a blanket try/except, or
      both) the implementation uses to satisfy it.
  CLI: `kiosk-perf-verdict.py <capture> [<baseline.json>] [<min_live>]
  [<capture_length>]`. baseline.json defaults to the committed tools/kiosk-perf-
  baseline.json beside this script; min_live defaults to 4 (parse_cards_probe's own
  stated default); capture_length defaults to 585.0 (review finding B2, refined:
  capture_length is a CLI argument, not fixed). Prints each reason (rc=1) or why it
  could not tell (rc=2), then one evidence line `regression reasons=<n>`, and exits
  with rc. This CLI shape is this test's own design, not spec-fixed.

Fixtures for Runs 73-75 (the fixed 2.54 image, S4) reconstruct the real MP| line from
the exact figures the README's "Metrics" tables report (sec, frames, bt, the bounded
stall-rate count pair, pct_under_50, fps) -- verified against parse_smoothness.py's
real functions before being trusted here. Their CP| series is a minimal reconstruction
of the qualitative facts the README states for that night (one pre-15s sample at t=4s,
c=0 l=0, excluded from the judged window; 19 judged samples with c=4 l=3 throughout --
"l never reaches 4, one park stays closed the whole capture"), NOT the literal raw
samples: those are retained off-tree, outside this repo. The README also states that
night's actual run used MIN_LIVE=3 (3/4 cards live, one closed), not this tool's
default of 4 -- passed explicitly for these three fixtures, flagged here because it is
the reason they read rc=0: at the default min_live=4, l=3 throughout would never
satisfy all_at_least and all three would read rc=2 instead.

tools/kiosk-perf-baseline.json (review finding S2) carries the EXACT (unrounded)
figures parse_smoothness.py produces from the committed real S1 captures
(docs/issue_investigation/wpe_evaluation/s1-smoothness-run{1,2,3}.txt -- Runs 2-4),
not the README's rounded Metrics-table figures (e.g. Run 3's pct_under_50 is
97.95578885110159, not the README's rounded 98.0). A dedicated case recomputes them
fresh from those capture files and compares against the committed JSON exactly.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import parse_smoothness as ps

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

PASS, FAIL = [], []


def case(name, got, want):
    (PASS if got == want else FAIL).append(name)
    if got != want:
        print(f"FAIL  {name}\n        want {want!r}\n        got  {got!r}")


def load(name):
    """kiosk-perf-verdict.py, imported by path: the filename is not a module name."""
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


perfv = load("kiosk-perf-verdict")

BASELINE = json.loads((TOOLS / "kiosk-perf-baseline.json").read_text())["runs"]


# --------------------------------------------------------------- fixtures

def cp_lines(t_values, c, l):
    return [f"CP|t={t}|c={c}|l={l}" for t in t_values]


# Runs 73-75: reconstructed from the README's "Metrics" tables (sec, frames, bt,
# stall-rate bound counts) -- confirmed against parse_smoothness.py's real functions
# to reproduce the exact reported figures (fps, pct_under_50, stall_rate bounds)
# before being trusted here.
RUN73_MP = ("MP|580|f29552|av20|mx1000|BT26|H29079.473.0.0.0.0.0|B20:300,40:300,60:300,"
            "80:300,100:300,120:300,140:300,160:300,180:300,200:300,220:300,240:300,"
            "260:300,280:300")
RUN74_MP = ("MP|581|f29737|av20|mx1000|BT26|H29231.506.0.0.0.0.0|B20:300,40:300,60:300,"
            "80:300,100:300,120:300,140:300,160:300,180:300,200:300,220:300,240:300,"
            "260:300,280:300")
RUN75_MP = ("MP|580|f29551|av20|mx1000|BT25|H29049.502.0.0.0.0.0|B20:300,40:300,60:300,"
            "80:300,100:300,120:300,140:300,160:300,180:300,200:300,220:300,240:300,"
            "260:300,280:300")

# One pre-15s sample (excluded), 19 judged samples at c=4 l=3 -- the night's actual
# reclassified result ("LIVE... l never reaches 4"), minimal reconstruction (not the
# literal off-tree raw samples).
REAL_NIGHT_CP = cp_lines([4], 0, 0) + cp_lines(range(30, 571, 30), 4, 3)

# B2 fixtures, hoisted to module level so both verdict_cases and the CLI cases can
# reuse them: a clean, fully-live CP| series, and an MP| payload whose sec (400) is
# well under 0.9x the default 585s capture length (526.5) but would read a clean
# pass against the baseline (pct_under_50=99.5, fps=50.0) if the length were not
# checked at all.
GOOD_CP = cp_lines([4], 4, 4) + cp_lines(range(30, 391, 30), 4, 4)
SHORT_MP = "MP|400|f20000|av50|mx500|BT0|H19900.100.0.0.0.0.0|B"


def verdict_cases():
    for name, mp_line in (("Run 73", RUN73_MP), ("Run 74", RUN74_MP), ("Run 75", RUN75_MP)):
        lines = [mp_line] + REAL_NIGHT_CP
        case(f"{name} (fixed 2.54) reads rc=0 against the X baseline, as the "
             f"investigation found",
             perfv.perf_verdict(lines, BASELINE, min_live=3),
             {"rc": 0, "reasons": []})

    # Synthetic regression: a candidate whose worst stall rate clearly exceeds the
    # baseline's own max (BU = max(0.0541, 0.0541, 0.0343) = 0.0541). sec=580 -- a
    # realistic capture length, so this case is not ALSO caught by the B2
    # capture-length gate below; only the stall rate is under test here.
    worse_mp = ("MP|580|f8000|av60|mx2000|BT50|H6000.2000.0.0.0.0.0"
                "|B20:300,30:300,40:300,50:300,60:300,70:300,80:300,90:300,100:300,"
                "110:300,120:300,130:300,140:300,150:300")
    result = perfv.perf_verdict([worse_mp] + REAL_NIGHT_CP, BASELINE, min_live=3)
    case("a clearly worse stall rate -> regression (rc=1)", result["rc"], 1)
    case("regression reasons is non-empty", len(result["reasons"]) > 0, True)

    # rc=2: no MP| payload at all in the capture.
    case("no MP| payload -> could not tell (rc=2)",
         perfv.perf_verdict(REAL_NIGHT_CP, BASELINE, min_live=3)["rc"], 2)

    # rc=2: the judged window (t >= 15) has a sample under min_live (default 4) --
    # run-s4-smoothness.sh's own cards gate, read as could-not-tell, never a pass.
    # Uses a clean, realistic-length MP| line (not one of the real-run fixtures) so
    # only the cards gate is under test, not ALSO the B2 capture-length gate below.
    clean_mp = ("MP|580|f6000|av50|mx500|BT2|H5000.600.300.80.15.4.1|B20:300,25:300")
    cards_drop = cp_lines([4], 0, 0) + cp_lines([20, 40, 60], 4, 4) + cp_lines([80], 4, 3)
    result = perfv.perf_verdict([clean_mp] + cards_drop, BASELINE, min_live=4)
    case("a judged sample under min_live -> could not tell, never a pass (rc=2)",
         result["rc"], 2)

    # rc=2: the judged window is empty (every CP| sample is before steady_from).
    all_pre_steady_cp = cp_lines([1, 5, 10], 4, 4)
    result = perfv.perf_verdict([clean_mp] + all_pre_steady_cp, BASELINE, min_live=4)
    case("an empty judged window -> could not tell (rc=2)", result["rc"], 2)

    # B2 (review finding): the MP| payload's own sec is well under 0.9 * the
    # nominal 585s capture length (526.5s) -- a restart or truncation signature,
    # not a short-but-real run (every real capture was 569-583s). hist and frame
    # count are chosen so pct_under_50 (99.5) and fps (50.0) would ALREADY read a
    # clean pass against the baseline if the length were not checked -- isolating
    # the length gate from any smoothness-rule finding. A clean, fully-live CP|
    # series over the same window does the same for the cards gate.
    result = perfv.perf_verdict([SHORT_MP] + GOOD_CP, BASELINE, min_live=4)
    case("MP| sec well under 0.9x the capture length -> could not tell (rc=2)",
         result["rc"], 2)

    # B2 edge case, refined (review finding): sec AT steady_from (15) -- span =
    # sec - steady_from = 0, which a naive steady_stall_bounds call would divide
    # by. A genuine judged CP| sample AT t=15 (c=4 l=4) isolates this from the
    # "empty judged window" rule. The CONTRACT under test is implementation-
    # agnostic: perf_verdict must never propagate this (or any other) exception
    # to its caller -- call it inside an explicit try/except here so a still-
    # unfixed implementation that lets the ZeroDivisionError through fails this
    # case on its own terms (got="EXCEPTION" != want=2) rather than crashing the
    # whole test script before any later case runs.
    edge_cp = cp_lines([4, 15], 4, 4)
    edge_mp = "MP|15|f750|av50|mx500|BT0|H740.10.0.0.0.0.0|B"
    try:
        got_rc = perfv.perf_verdict([edge_mp] + edge_cp, BASELINE, min_live=4)["rc"]
    except Exception:
        got_rc = "EXCEPTION"
    case("MP| sec == steady_from -> could not tell (rc=2), never an exception",
         got_rc, 2)

    # S2 (review finding): tools/kiosk-perf-baseline.json must carry the EXACT
    # (unrounded) parse_smoothness figures for the real S1 captures, not the
    # README's rounded Metrics-table numbers. Recomputed fresh here from the
    # committed capture files -- never hand-copied -- and compared exactly.
    s1_dir = TOOLS.parent / "docs/issue_investigation/wpe_evaluation"
    recomputed = []
    for fname in ("s1-smoothness-run1.txt", "s1-smoothness-run2.txt",
                  "s1-smoothness-run3.txt"):
        text = (s1_dir / fname).read_text()
        line = next(l for l in text.splitlines() if "MP|" in l)
        d = ps.parse(line)
        b = ps.steady_stall_bounds(d)
        recomputed.append({
            "fps": ps.mean_fps(d),
            "pct_under_50": ps.pct_under_50ms(d),
            "stall_rate": {"lower_rate": b["lower_rate"], "upper_rate": b["upper_rate"],
                           "bounded": b["bounded"]},
        })
    case("kiosk-perf-baseline.json matches a fresh recompute from the real S1 "
         "captures, exactly",
         BASELINE, recomputed)


# ------------------------------------------------------------------- CLI

def run_cli(capture, baseline=None, min_live=None, capture_length=None):
    argv = [sys.executable, str(TOOLS / "kiosk-perf-verdict.py"), str(capture)]
    # Each later positional needs every earlier slot filled with the committed
    # default when it is itself wanted but an earlier arg was not overridden, or
    # it would land in the wrong argv slot.
    if baseline is not None or min_live is not None or capture_length is not None:
        argv.append(str(baseline) if baseline is not None
                    else str(TOOLS / "kiosk-perf-baseline.json"))
    if min_live is not None or capture_length is not None:
        argv.append(str(min_live) if min_live is not None else "4")
    if capture_length is not None:
        argv.append(str(capture_length))
    return subprocess.run(argv, capture_output=True, text=True)


def cli_cases(tmp_path):
    tmp = Path(tmp_path)
    capture = tmp / "capture.txt"
    capture.write_text("\n".join([RUN73_MP] + REAL_NIGHT_CP) + "\n")
    got = run_cli(capture, min_live=3)
    case("CLI: rc=0 against the committed baseline.json (no override)", got.returncode, 0)
    case("CLI: evidence line names the reason count",
         "regression reasons=0" in got.stdout.splitlines(), True)

    cant_tell_capture = tmp / "cant-tell.txt"
    cant_tell_capture.write_text("\n".join(REAL_NIGHT_CP) + "\n")
    got = run_cli(cant_tell_capture, min_live=3)
    case("CLI: no MP| payload exits 2", got.returncode, 2)

    # B2 (review finding, refined): capture_length is a CLI argument, not a
    # fixed 585 -- the SAME SHORT_MP capture (sec=400) reads rc=2 under the
    # default 585s capture length (400 is well under 0.9*585=526.5) and rc=0
    # under an explicit 440s capture length (400 >= 0.9*440=396, and the
    # payload is otherwise clean). Proves the CLI actually threads the
    # argument through, not a hardcoded 585.
    short_capture = tmp / "short-length.txt"
    short_capture.write_text("\n".join([SHORT_MP] + GOOD_CP) + "\n")
    got = run_cli(short_capture, min_live=4)
    case("CLI: SHORT_MP under the default 585s capture length -> rc=2",
         got.returncode, 2)
    got = run_cli(short_capture, min_live=4, capture_length=440)
    case("CLI: the SAME capture clears an explicit 440s capture length -> rc=0",
         got.returncode, 0)


def main() -> int:
    verdict_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cli_cases(tmp)
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
