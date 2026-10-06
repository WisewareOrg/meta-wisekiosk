#!/usr/bin/env python3
"""Self-test for kiosk-stability-verdict.py, the one-instrument soak check bench runs
and the pipeline both use. Run by hand -- not wired into just guards or ci-guards.sh.

    kiosk-stability-verdict-test.py    -- every case, both directions

THE CONTRACT THIS PINS, since kiosk-stability-verdict.py does not exist yet and this
test is what fixes its shape:

  stability_verdict(mf_lines, restarts, reboots, oom_lines, window=3600.0,
                    sample_interval=30.0)
      -> {"rc": 0|1|2, "reasons": [str, ...]}

  mf_lines: a soak capture's raw text lines, carrying mf-probe.js's MF| samples (one
  every 30 s through the soak).
  restarts, reboots: int counts over the soak (kiosk-soak.sh's own sampler already
  detects these).
  oom_lines: int count of OOM-killer lines over the soak. There is no separately
  passed memory_problem boolean: the plan's memory rule ("a regression is an OOM-
  killer line or a memory-attributed restart") IS the definition --
  memory_problem = oom_lines > 0, computed here, never taken as an input. Swap,
  RSS and PSI are printed elsewhere, never judged by this tool.

  Processing, reusing the moved tools AS THEY ARE:
  - parse_module_fault.soak_summary(mf_lines) gives {"fmax", "fever", "umax"}.
  - candidate_soak = {"fmax": summary["fmax"], "fever": summary["fever"],
    "restarts": restarts, "reboots": reboots, "memory_problem": oom_lines > 0}.
  - baseline_soak is the ZERO baseline (team-lead's own wording): {"fmax": 0,
    "fever": 0, "restarts": 0, "reboots": 0, "memory_problem": False} -- the ideal
    soak, not a measured X baseline file.
  - reasons = verdict.regression_reasons(NEUTRAL_RUNS, NEUTRAL_RUNS, baseline_soak,
    candidate_soak) -- the SAME neutral smoothness runs on both sides so no
    smoothness-side reason can ever fire, leaving only the soak rules (fmax, fever,
    restarts, reboots, memory_problem) live; oom_lines > 0 reaches
    regression_reasons' OWN existing "memory problem signal in the candidate soak"
    reason through memory_problem, with no separate reason string needed. Reuses
    regression_reasons whole, mirror of kiosk-perf-verdict.py's own neutral-soak
    trick; the neutral-runs shape is this test's own design, not spec-fixed.

  rc=0: no regression (reasons == []).
  rc=1: regression (reasons is the printed list).
  rc=2 (could not tell), in ANY of these cases:
    - soak_summary raises ValueError on zero parseable MF| samples;
    - the count of parseable MF| samples < 0.9 * floor(window / sample_interval)
      (review finding B1: for the default 3600s/30s window that is 108; the real
      soaks had 117-121. A single sample reads rc=2, not a pass -- the probe
      having run once is not the same as it having run through the soak);
    - the LAST parseable MF| sample's own t < window - 60 (review finding B1,
      refined: a sufficient sample COUNT alone does not prove the soak ran the
      full window -- a probe that sampled densely then stopped early must not
      read as complete). The two rules are independent gates; either firing
      alone is rc=2.
  The previously-asked "sample gap" rule still does not exist in parse_module_
  fault.py, and the owner has confirmed it is not wanted on its own: a single
  missing sample mid-soak was recorded as a finding in Run 8, never a VOID --
  the count-floor and last-t checks are DIFFERENT, coarser rules (too few
  samples overall; stopped too early), not a gap-between-consecutive-samples
  check.

  CLI: `kiosk-stability-verdict.py <capture> <restarts> <reboots> <oom-lines>
  <window>`. window (SECS) is a required CLI argument (review finding B1,
  refined), not a fixed 3600 -- sample_interval stays at its 30s default and
  is not CLI-exposed. Prints each reason (rc=1) or why it could not tell
  (rc=2), then one evidence line `regression reasons=<n>`, and exits with rc.
  This CLI shape is this test's own design, not spec-fixed.

Run 76 (the fixed 2.54 soak) and Run 8 (the X baseline soak) are reconstructed as
full 121-sample series (t=0,30,...,3600 -- one every 30s through the 3600s window,
matching the real soaks' own cadence and comfortably past the 108-sample floor),
with fmax/fever/umax held at the README's reported peaks (Run 76: umax=1 at one
sample; Run 8: all zero) and zero everywhere else -- not the literal raw captures,
but enough samples to exercise the B1 floor honestly rather than sidestepping it.
oom_lines=0 for both, matching the README's own zero OOM-line counts. The purely
synthetic REGRESSED_MF fixture stays minimal with an explicitly smaller window,
since it makes no claim to real-soak fidelity.
"""
import importlib.util
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
    """kiosk-stability-verdict.py, imported by path: the filename is not a module
    name."""
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stabv = load("kiosk-stability-verdict")


# --------------------------------------------------------------- fixtures

def mf_series(window=3600, interval=30, peak_at=None, fmax=0, fever=0, umax=0):
    """One MF| line every `interval` seconds through [0, window] -- 121 lines for
    the default 3600/30 -- all zero except the single sample at `peak_at`, which
    carries the given peak figures. Enough real samples to clear the B1 floor
    honestly, not a token few."""
    lines = []
    t = 0
    while t <= window:
        if peak_at is not None and t == peak_at:
            lines.append(f"MF|t={t}|f=0|fmax={fmax}|fever={fever}|u=0|umax={umax}")
        else:
            lines.append(f"MF|t={t}|f=0|fmax=0|fever=0|u=0|umax=0")
        t += interval
    return lines


# Run 76 (fixed 2.54 soak): fmax=0, fever=0, umax=1, restarts=0, reboots=0, OOM
# lines=0. 121 samples (t=0..3600 every 30s), proven against parse_module_fault's
# real soak_summary to reproduce these exact figures.
RUN76_MF = mf_series(peak_at=1800, umax=1)

# Run 8 (the X baseline soak): fmax=0, fever=0, umax=0 -- also 121 samples, all
# zero. Also reads rc=0 against the zero baseline, since its own figures ARE
# zero; proves the zero baseline is not special-cased to only accept Run 76.
RUN8_MF = mf_series()

# A clear regression: fmax and fever both exceed the zero baseline. Purely
# synthetic (not a named real run), so it stays minimal with an explicitly
# smaller window (60s/30s = 2 samples, floor*0.9 = 1.8) rather than padding to
# 121 lines it makes no claim to.
REGRESSED_MF = [
    "MF|t=0|f=0|fmax=0|fever=0|u=0|umax=0",
    "MF|t=30|f=2|fmax=2|fever=3|u=0|umax=0",
]
REGRESSED_WINDOW = 60


def series_with_last_t(count, last_t, interval=9):
    """`count` MF| lines, chronological, the first count-1 spaced `interval`
    seconds apart starting at t=0 and the final one forced to t=last_t (so
    last_t is unambiguously both the file's last line and the maximum t).
    Isolates the last-t rule from the count rule: pick count high enough to
    clear the count floor on its own while last_t falls short of window-60."""
    lines = [f"MF|t={i * interval}|f=0|fmax=0|fever=0|u=0|umax=0"
             for i in range(count - 1)]
    lines.append(f"MF|t={last_t}|f=0|fmax=0|fever=0|u=0|umax=0")
    return lines


# B1 (review finding, refined): 108 samples clears the default 3600s/30s
# count floor (0.9 * floor(3600/30) = 108, and 108 is not < 108) on its own,
# but the last sample's own t=1070 is nowhere near window-60=3540 -- the soak
# sampled densely, then stopped three-quarters of the way through the window.
STOPPED_EARLY_MF = series_with_last_t(count=108, last_t=1070)

# The boundary this contrasts with: same 108-sample count, last t placed
# exactly on the window-60 line (3540) -- the rule is "t >= window - 60", so
# this must still read rc=0 (not a false rc=2 at the boundary).
BOUNDARY_LAST_T_MF = series_with_last_t(count=108, last_t=3540)


def verdict_cases():
    case("Run 76 (fixed 2.54 soak) reads rc=0 against the zero baseline, as the "
         "investigation found",
         stabv.stability_verdict(RUN76_MF, restarts=0, reboots=0, oom_lines=0),
         {"rc": 0, "reasons": []})

    case("Run 8 (X baseline soak) also reads rc=0 against the zero baseline",
         stabv.stability_verdict(RUN8_MF, restarts=0, reboots=0, oom_lines=0),
         {"rc": 0, "reasons": []})

    result = stabv.stability_verdict(REGRESSED_MF, restarts=0, reboots=0, oom_lines=0,
                                      window=REGRESSED_WINDOW)
    case("higher fmax/fever -> regression (rc=1)", result["rc"], 1)
    case("regression reasons mention fmax and fever",
         any("fmax" in r.lower() or "simultaneous" in r.lower() for r in result["reasons"])
         and any("fever" in r.lower() or "ever-seen" in r.lower() for r in result["reasons"]),
         True)

    result = stabv.stability_verdict(RUN76_MF, restarts=1, reboots=0, oom_lines=0)
    case("a restart against the zero baseline -> regression (rc=1)", result["rc"], 1)

    # memory_problem is NOT a separately passed input: it is oom_lines > 0. A
    # nonzero OOM-killer-line count is itself a regression, absolute, even with
    # zero fmax/fever/restarts/reboots -- the plan's rule IS the definition, not
    # a flag decided elsewhere.
    result = stabv.stability_verdict(RUN76_MF, restarts=0, reboots=0, oom_lines=5)
    case("oom_lines > 0 alone -> regression (rc=1), absolute", result["rc"], 1)
    case("the regression reason names the memory problem",
         any("memory" in r.lower() or "oom" in r.lower() for r in result["reasons"]),
         True)

    # Zero OOM lines must not themselves cause a regression (the boundary this
    # contrasts with) -- memory_problem derives to False.
    result = stabv.stability_verdict(RUN76_MF, restarts=0, reboots=0, oom_lines=0)
    case("oom_lines=0 -> no memory-problem reason", result, {"rc": 0, "reasons": []})

    # rc=2: no MF| samples parse at all.
    case("no MF| samples -> could not tell, never a pass (rc=2)",
         stabv.stability_verdict(["no MF| payload here"], restarts=0, reboots=0,
                                  oom_lines=0)["rc"],
         2)

    # B1 (review finding): a single sample over the default 3600s/30s window is
    # nowhere near the 108-sample floor (0.9 * floor(3600/30)) -- the probe
    # having run once is not the same as it having run through the soak. Not
    # the "zero samples" ValueError path: soak_summary would happily compute
    # fmax/fever from this one line.
    case("a single sample over the full 3600s window -> could not tell, never a pass",
         stabv.stability_verdict(["MF|t=0|f=0|fmax=0|fever=0|u=0|umax=0"],
                                  restarts=0, reboots=0, oom_lines=0)["rc"],
         2)

    # The boundary this contrasts with: Run 76's own 121 samples, comfortably
    # over the 108 floor, already reads rc=0 above -- proving the floor does
    # not reject a genuinely complete soak.

    # B1 (review finding, refined): the last-t rule, isolated from the count
    # rule. 108 samples clears the count floor outright, but the soak's last
    # sample (t=1070) is far short of window-60=3540 -- it stopped early.
    case("count clears the floor but the soak stopped early (last t=1070 "
         "< window-60=3540) -> could not tell, never a pass",
         stabv.stability_verdict(STOPPED_EARLY_MF, restarts=0, reboots=0,
                                  oom_lines=0)["rc"],
         2)

    # The boundary this contrasts with: last t placed exactly on window-60
    # (3540, not short of it) must read rc=0 -- the rule is t >= window-60,
    # not strictly greater.
    case("last t exactly at window-60 (3540) -> not early, reads rc=0",
         stabv.stability_verdict(BOUNDARY_LAST_T_MF, restarts=0, reboots=0,
                                  oom_lines=0),
         {"rc": 0, "reasons": []})


# ------------------------------------------------------------------- CLI

def run_cli(capture, restarts=0, reboots=0, oom_lines=0, window=3600):
    return subprocess.run(
        [sys.executable, str(TOOLS / "kiosk-stability-verdict.py"), str(capture),
         str(restarts), str(reboots), str(oom_lines), str(window)],
        capture_output=True, text=True)


def cli_cases(tmp_path):
    tmp = Path(tmp_path)
    capture = tmp / "run76.txt"
    capture.write_text("\n".join(RUN76_MF) + "\n")
    got = run_cli(capture, window=3600)
    case("CLI: Run 76 exits 0", got.returncode, 0)
    case("CLI: evidence line names the reason count",
         "regression reasons=0" in got.stdout.splitlines(), True)

    empty_capture = tmp / "empty.txt"
    empty_capture.write_text("no MF| payload here\n")
    got = run_cli(empty_capture, window=3600)
    case("CLI: no MF| samples exits 2", got.returncode, 2)

    # B1 (review finding, refined): window (SECS) is a required CLI argument,
    # not a fixed 3600 -- the SAME 10-sample capture reads rc=0 under a 120s
    # window (10 samples clears a 120s-scaled count floor of 3.6, and the
    # last t=135 clears window-60=60) and rc=2 under a 3600s window (10
    # samples is nowhere near the 108-sample floor). Proves the CLI actually
    # threads the argument through, not a hardcoded 3600.
    short_capture = tmp / "short-window.txt"
    short_capture.write_text("\n".join(
        f"MF|t={t}|f=0|fmax=0|fever=0|u=0|umax=0" for t in range(0, 136, 15)) + "\n")
    got = run_cli(short_capture, window=120)
    case("CLI: 10 samples clear a 120s window's own floor and last-t rule "
         "-> rc=0", got.returncode, 0)
    got = run_cli(short_capture, window=3600)
    case("CLI: the SAME capture fails the 3600s window's floor -> rc=2",
         got.returncode, 2)


def main() -> int:
    verdict_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cli_cases(tmp)
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
