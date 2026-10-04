#!/usr/bin/env python3
"""RED tests for parse_module_fault, the #185 module-fault probe parser.

parse_module_fault does not exist yet -- this file is the spec code-monkey makes green.

Payload format (NEW probe; no in-tree precedent existed, so wpe-tests proposed it and the
orchestrator ruled it binding on #185 2026-10-04 -- it binds the title-channel emitter on X
and the console-to-journal emitter on WPE equally, so this one parser reads both):

    MF|t=<sec>|f=<n>|fmax=<n>|fever=<n>|u=<n>|umax=<n>

  t      seconds since page load (int)
  f      [data-module-faulted] elements present RIGHT NOW (this sample)
  fmax   max simultaneous [data-module-faulted] count ever seen this session (running max,
         maintained by the in-page probe itself, like p7_min.js's BT)
  fever  count of DISTINCT [data-module-faulted] elements ever seen this session
  u      [data-module-unavailable] elements present right now -- recorded, not judged
  umax   max simultaneous [data-module-unavailable] ever seen -- recorded, not judged

The probe is sampled every 30s through the 1h soak (#185 plan "Module-fault metric"), so a
soak capture holds MANY MF| lines, not one. fmax/fever/umax are running maxima inside the
page's own JS, so they should be monotonic non-decreasing across one unbroken session -- but
a kiosk restart resets the page (and its running maxima) to zero mid-soak, exactly as
kiosk-soak.sh's own sampler already detects restarts separately. soak_summary must take the
MAX across all samples, never just the last one, so a restart can never hide an earlier high
reading.

Run: python3 parse_module_fault_test.py
"""
import parse_module_fault as pmf

fails = 0


def check(name, cond, detail=""):
    global fails
    status = "PASS" if cond else "FAIL"
    if not cond:
        fails += 1
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))


SAMPLE = "MF|t=120|f=1|fmax=2|fever=3|u=0|umax=1"
MALFORMED = "MF|t=120|f=1"
NOT_A_PAYLOAD = "the quick brown fox"

# A soak run with NO restart: fmax/fever climb monotonically. Last sample holds the max.
MONOTONIC = [
    "MF|t=0|f=0|fmax=0|fever=0|u=0|umax=0",
    "MF|t=1800|f=1|fmax=1|fever=1|u=0|umax=0",
    "MF|t=3600|f=2|fmax=2|fever=4|u=1|umax=1",
]

# A soak run WITH a mid-run restart: fmax/fever hit a peak, then the browser restarts and
# the page's running counters reset to a smaller value. The true session max is the PEAK,
# not the (smaller) final sample -- a parser that trusts only the last line gets this wrong.
WITH_RESTART = [
    "MF|t=0|f=0|fmax=0|fever=0|u=0|umax=0",
    "MF|t=1800|f=3|fmax=5|fever=7|u=2|umax=3",   # peak before the restart
    "MF|t=1830|f=0|fmax=0|fever=0|u=0|umax=0",   # page reloaded, counters reset
    "MF|t=3600|f=1|fmax=1|fever=1|u=0|umax=0",   # never catches back up to the peak
]


def test_parse_sample():
    d = pmf.parse(SAMPLE)
    check("parse(SAMPLE) returns a dict", d is not None)
    check("parse(SAMPLE).t", d["t"] == 120)
    check("parse(SAMPLE).f", d["f"] == 1)
    check("parse(SAMPLE).fmax", d["fmax"] == 2)
    check("parse(SAMPLE).fever", d["fever"] == 3)
    check("parse(SAMPLE).u", d["u"] == 0)
    check("parse(SAMPLE).umax", d["umax"] == 1)


def test_parse_rejects_malformed():
    check("parse(MALFORMED) is None", pmf.parse(MALFORMED) is None)
    check("parse(NOT_A_PAYLOAD) is None", pmf.parse(NOT_A_PAYLOAD) is None)


def test_soak_summary_monotonic_run():
    s = pmf.soak_summary(MONOTONIC)
    check("soak_summary(MONOTONIC).fmax == 2", s["fmax"] == 2)
    check("soak_summary(MONOTONIC).fever == 4", s["fever"] == 4)
    check("soak_summary(MONOTONIC).umax == 1", s["umax"] == 1)


def test_soak_summary_survives_a_mid_run_restart():
    s = pmf.soak_summary(WITH_RESTART)
    # The peak (fmax=5, fever=7, umax=3) occurred before the restart. A summary that only
    # reads the last line would report fmax=1, fever=1, umax=0 -- wrong. This is the check
    # that catches that bug.
    check("soak_summary(WITH_RESTART).fmax == 5 (peak, not last-sample's 1)",
          s["fmax"] == 5, detail=str(s))
    check("soak_summary(WITH_RESTART).fever == 7 (peak, not last-sample's 1)",
          s["fever"] == 7, detail=str(s))
    check("soak_summary(WITH_RESTART).umax == 3 (peak, not last-sample's 0)",
          s["umax"] == 3, detail=str(s))


def test_soak_summary_skips_unparseable_lines():
    lines = ["# a comment line, not MF|", MALFORMED, "MF|t=10|f=0|fmax=1|fever=1|u=0|umax=0"]
    s = pmf.soak_summary(lines)
    check("soak_summary skips noise and reads the one good line",
          s["fmax"] == 1 and s["fever"] == 1 and s["umax"] == 0, detail=str(s))


if __name__ == "__main__":
    test_parse_sample()
    test_parse_rejects_malformed()
    test_soak_summary_monotonic_run()
    test_soak_summary_survives_a_mid_run_restart()
    test_soak_summary_skips_unparseable_lines()
    print()
    if fails:
        raise SystemExit(f"{fails} check(s) FAILED")
    print("all checks passed")
