#!/usr/bin/env python3
"""Self-test for kiosk-stability-verdict.py, the one-instrument soak check bench runs
and the pipeline both use. Run by hand -- not wired into just guards or ci-guards.sh.

    kiosk-stability-verdict-test.py    -- every case, both directions

THE CONTRACT THIS PINS, since kiosk-stability-verdict.py does not exist yet and this
test is what fixes its shape:

  stability_verdict(mf_lines, restarts, reboots, oom_lines, memory_problem)
      -> {"rc": 0|1|2, "reasons": [str, ...]}

  mf_lines: a soak capture's raw text lines, carrying mf-probe.js's MF| samples (one
  every 30 s through the soak).
  restarts, reboots: int counts over the soak (kiosk-soak.sh's own sampler already
  detects these).
  oom_lines: int count of OOM-killer lines in the journal. JUDGED (owner-approved
  plan's memory rule: "a regression is an OOM-killer line or a memory-attributed
  restart"): oom_lines > 0 is itself a regression, same ABSOLUTE treatment as
  memory_problem -- not compared against a baseline count. Since verdict.
  regression_reasons has no oom_lines parameter at all, this tool adds its own
  reason string when oom_lines > 0, alongside whatever regression_reasons itself
  returns.
  memory_problem: bool, already decided elsewhere (kiosk-soak.sh's own memory
  reporting) -- this tool consumes it, it does not derive it from MemAvailable/slope/
  swap/PSI.

  Processing, reusing the moved tools AS THEY ARE:
  - parse_module_fault.soak_summary(mf_lines) gives {"fmax", "fever", "umax"}.
  - candidate_soak = {"fmax": summary["fmax"], "fever": summary["fever"],
    "restarts": restarts, "reboots": reboots, "memory_problem": memory_problem}.
  - baseline_soak is the ZERO baseline (team-lead's own wording): {"fmax": 0,
    "fever": 0, "restarts": 0, "reboots": 0, "memory_problem": False} -- the ideal
    soak, not a measured X baseline file.
  - reasons = verdict.regression_reasons(NEUTRAL_RUNS, NEUTRAL_RUNS, baseline_soak,
    candidate_soak) -- the SAME neutral smoothness runs on both sides so no
    smoothness-side reason can ever fire, leaving only the soak rules (fmax, fever,
    restarts, reboots, memory_problem) live. Reuses regression_reasons whole, mirror
    of kiosk-perf-verdict.py's own neutral-soak trick; the neutral-runs shape is this
    test's own design, not spec-fixed.
  - if oom_lines > 0: reasons gets this tool's own extra reason string, naming the
    count -- this test's own design for the exact wording, not spec-fixed.

  rc=0: no regression (reasons == []).
  rc=1: regression (reasons is the printed list).
  rc=2 (could not tell): soak_summary raises ValueError on zero parseable MF|
  samples. This is the ONLY rc=2 trigger -- the previously-asked "sample gap" rule
  does not exist in parse_module_fault.py (confirmed no rule there), and the owner
  has confirmed it is not wanted: a single missing sample was recorded as a finding
  in Run 8, never a VOID.

  CLI: `kiosk-stability-verdict.py <capture> <restarts> <reboots> <oom-lines>
  <memory-problem 0|1>`. Prints each reason (rc=1) or why it could not tell (rc=2),
  then one evidence line `regression reasons=<n>`, and exits with rc. This CLI shape
  is this test's own design, not spec-fixed.

Run 76 (the fixed 2.54 soak) is reconstructed from the README's "Metrics" table
(fmax=0, fever=0, umax=1, restarts=0, reboots=0, OOM lines=0) with a minimal 3-line
MF| series proven against parse_module_fault.py's real soak_summary to reproduce
those exact fmax/fever/umax figures -- not the literal 121 samples the real capture
held. memory_problem=False for this fixture: the README records zero OOM lines and
no other stated memory-problem signal for Run 76.
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

# Run 76 (fixed 2.54 soak): fmax=0, fever=0, umax=1, restarts=0, reboots=0, OOM
# lines=0 -- a minimal 3-line series proven to reproduce these exact figures via
# parse_module_fault.soak_summary, not the real capture's literal 121 samples.
RUN76_MF = [
    "MF|t=0|f=0|fmax=0|fever=0|u=0|umax=0",
    "MF|t=1800|f=0|fmax=0|fever=0|u=1|umax=1",
    "MF|t=3600|f=0|fmax=0|fever=0|u=0|umax=1",
]

# Run 8 (the X baseline soak): fmax=0, fever=0, umax=0, restarts=0, reboots=0, OOM
# lines=0 -- also reads rc=0 against the zero baseline, since its own figures ARE
# zero; proves the zero baseline is not special-cased to only accept Run 76.
RUN8_MF = [
    "MF|t=0|f=0|fmax=0|fever=0|u=0|umax=0",
    "MF|t=1800|f=0|fmax=0|fever=0|u=0|umax=0",
    "MF|t=3600|f=0|fmax=0|fever=0|u=0|umax=0",
]

# A clear regression: fmax and fever both exceed the zero baseline.
REGRESSED_MF = [
    "MF|t=0|f=0|fmax=0|fever=0|u=0|umax=0",
    "MF|t=1800|f=2|fmax=2|fever=3|u=0|umax=0",
]


def verdict_cases():
    case("Run 76 (fixed 2.54 soak) reads rc=0 against the zero baseline, as the "
         "investigation found",
         stabv.stability_verdict(RUN76_MF, restarts=0, reboots=0, oom_lines=0,
                                  memory_problem=False),
         {"rc": 0, "reasons": []})

    case("Run 8 (X baseline soak) also reads rc=0 against the zero baseline",
         stabv.stability_verdict(RUN8_MF, restarts=0, reboots=0, oom_lines=0,
                                  memory_problem=False),
         {"rc": 0, "reasons": []})

    result = stabv.stability_verdict(REGRESSED_MF, restarts=0, reboots=0, oom_lines=0,
                                      memory_problem=False)
    case("higher fmax/fever -> regression (rc=1)", result["rc"], 1)
    case("regression reasons mention fmax and fever",
         any("fmax" in r.lower() or "simultaneous" in r.lower() for r in result["reasons"])
         and any("fever" in r.lower() or "ever-seen" in r.lower() for r in result["reasons"]),
         True)

    result = stabv.stability_verdict(RUN76_MF, restarts=1, reboots=0, oom_lines=0,
                                      memory_problem=False)
    case("a restart against the zero baseline -> regression (rc=1)", result["rc"], 1)

    result = stabv.stability_verdict(RUN76_MF, restarts=0, reboots=0, oom_lines=0,
                                      memory_problem=True)
    case("memory_problem=True -> regression (rc=1), absolute, not baseline-relative",
         result["rc"], 1)

    # oom_lines is JUDGED (owner-approved plan's memory rule): a nonzero count is
    # itself a regression, absolute, even with memory_problem=False and zero
    # fmax/fever/restarts/reboots -- an OOM-killer line is its own reason, not
    # gated behind the separate memory_problem flag.
    result = stabv.stability_verdict(RUN76_MF, restarts=0, reboots=0, oom_lines=5,
                                      memory_problem=False)
    case("oom_lines > 0 alone -> regression (rc=1), absolute", result["rc"], 1)
    case("oom_lines regression reason names OOM",
         any("oom" in r.lower() for r in result["reasons"]), True)

    # Zero OOM lines must not themselves cause a regression (the boundary this
    # contrasts with).
    result = stabv.stability_verdict(RUN76_MF, restarts=0, reboots=0, oom_lines=0,
                                      memory_problem=False)
    case("oom_lines=0 -> no OOM-line reason", result, {"rc": 0, "reasons": []})

    # rc=2: no MF| samples parse at all.
    case("no MF| samples -> could not tell, never a pass (rc=2)",
         stabv.stability_verdict(["no MF| payload here"], restarts=0, reboots=0,
                                  oom_lines=0, memory_problem=False)["rc"],
         2)


# ------------------------------------------------------------------- CLI

def run_cli(capture, restarts=0, reboots=0, oom_lines=0, memory_problem=0):
    return subprocess.run(
        [sys.executable, str(TOOLS / "kiosk-stability-verdict.py"), str(capture),
         str(restarts), str(reboots), str(oom_lines), str(memory_problem)],
        capture_output=True, text=True)


def cli_cases(tmp_path):
    tmp = Path(tmp_path)
    capture = tmp / "run76.txt"
    capture.write_text("\n".join(RUN76_MF) + "\n")
    got = run_cli(capture)
    case("CLI: Run 76 exits 0", got.returncode, 0)
    case("CLI: evidence line names the reason count",
         "regression reasons=0" in got.stdout.splitlines(), True)

    empty_capture = tmp / "empty.txt"
    empty_capture.write_text("no MF| payload here\n")
    got = run_cli(empty_capture)
    case("CLI: no MF| samples exits 2", got.returncode, 2)


def main() -> int:
    verdict_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cli_cases(tmp)
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
