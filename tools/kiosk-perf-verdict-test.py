#!/usr/bin/env python3
"""Self-test for kiosk-perf-verdict.py, the one-instrument smoothness check bench runs
and the pipeline both use. Run by hand -- not wired into just guards or ci-guards.sh.

    kiosk-perf-verdict-test.py    -- every case, both directions

THE CONTRACT THIS PINS, since kiosk-perf-verdict.py does not exist yet and this test is
what fixes its shape:

  perf_verdict(lines, baseline_runs, min_live=4, steady_from=15.0)
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
  rc=2 (could not tell), in EITHER of these cases:
    - no MP| payload parses in the whole capture;
    - the judged CP| window (t >= steady_from) is empty, or any sample in it has
      l < min_live -- run-s4-smoothness.sh's own cards gate, read as could-not-tell,
      never a pass. (A third rc=2 trigger, "capture too short", is not yet determined
      by parse_smoothness.py's own code and is deliberately NOT encoded here --
      halted and asked separately.)

  CLI: `kiosk-perf-verdict.py <capture> [<baseline.json>] [<min_live>]`. baseline.json
  defaults to the committed tools/kiosk-perf-baseline.json beside this script;
  min_live defaults to 4 (parse_cards_probe's own stated default). Prints each reason
  (rc=1) or why it could not tell (rc=2), then one evidence line `regression
  reasons=<n>`, and exits with rc. This CLI shape is this test's own design, not
  spec-fixed.

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
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

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


def verdict_cases():
    for name, mp_line in (("Run 73", RUN73_MP), ("Run 74", RUN74_MP), ("Run 75", RUN75_MP)):
        lines = [mp_line] + REAL_NIGHT_CP
        case(f"{name} (fixed 2.54) reads rc=0 against the X baseline, as the "
             f"investigation found",
             perfv.perf_verdict(lines, BASELINE, min_live=3),
             {"rc": 0, "reasons": []})

    # Synthetic regression: a candidate whose worst stall rate clearly exceeds the
    # baseline's own max (BU = max(0.0541, 0.0541, 0.0343) = 0.0541).
    worse_mp = ("MP|200|f8000|av60|mx2000|BT50|H6000.2000.0.0.0.0.0"
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
    # Uses a clean MP| line (not one of the real-run fixtures) so only the cards gate
    # is under test.
    clean_mp = ("MP|100|f6000|av50|mx500|BT2|H5000.600.300.80.15.4.1|B20:300,25:300")
    cards_drop = cp_lines([4], 0, 0) + cp_lines([20, 40, 60], 4, 4) + cp_lines([80], 4, 3)
    result = perfv.perf_verdict([clean_mp] + cards_drop, BASELINE, min_live=4)
    case("a judged sample under min_live -> could not tell, never a pass (rc=2)",
         result["rc"], 2)

    # rc=2: the judged window is empty (every CP| sample is before steady_from).
    all_pre_steady_cp = cp_lines([1, 5, 10], 4, 4)
    result = perfv.perf_verdict([clean_mp] + all_pre_steady_cp, BASELINE, min_live=4)
    case("an empty judged window -> could not tell (rc=2)", result["rc"], 2)


# ------------------------------------------------------------------- CLI

def run_cli(capture, baseline=None, min_live=None):
    argv = [sys.executable, str(TOOLS / "kiosk-perf-verdict.py"), str(capture)]
    # min_live is positional AFTER baseline -- if it is wanted but baseline is not
    # overridden, the committed default must still be passed explicitly, or min_live
    # would land in baseline's own argv slot.
    if baseline is not None or min_live is not None:
        argv.append(str(baseline) if baseline is not None
                    else str(TOOLS / "kiosk-perf-baseline.json"))
    if min_live is not None:
        argv.append(str(min_live))
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


def main() -> int:
    verdict_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cli_cases(tmp)
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
