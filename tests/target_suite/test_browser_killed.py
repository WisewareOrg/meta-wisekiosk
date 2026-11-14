"""Target suite: the browser killed with nobody at the panel is back on the panel in time."""

import subprocess
import time

from verdicts.browser_restart import verdict

# TST001's bound
_BOUND_SECONDS = 15
# stop polling; past the bound, so the record still carries the time it took
_GIVE_UP_SECONDS = 120


def test_browser_killed(board, panel, record_property):
    """TST001 browser killed: SIGKILL the browser and time until the instance is on the panel again."""
    _, before = panel.wait_on_panel()

    stdout, _stderr, _returncode = board.run(
        "cat /proc/uptime; kill -KILL $(pgrep -x surf)", check=True
    )
    killed_at = float(stdout[0].split()[0])
    killed_mono = time.monotonic()

    samples = []
    outcome, reason = "not-restarted", ""
    recovered_s = None
    while True:
        try:
            uptime_s, sample = panel.read()
        except subprocess.TimeoutExpired:
            uptime_s, sample = None, None
        samples.append(sample)
        outcome, reason = verdict(before, samples)
        if outcome == "restarted":
            recovered_s = round(uptime_s - killed_at, 1)
            break
        if time.monotonic() - killed_mono > _GIVE_UP_SECONDS:
            break
        if uptime_s is not None and uptime_s - killed_at > _GIVE_UP_SECONDS:
            break
        time.sleep(0.5)

    record_property("before", before)
    record_property("after", samples[-1])
    record_property("killed_at_uptime_s", killed_at)
    record_property("recovered_s", recovered_s)

    if outcome == "error":
        raise RuntimeError(reason)
    assert outcome == "restarted", f"the instance did not come back on the panel: {reason}"
    assert recovered_s <= _BOUND_SECONDS, (
        f"back on the panel after {recovered_s} s; TST001's bound is {_BOUND_SECONDS} s"
    )
