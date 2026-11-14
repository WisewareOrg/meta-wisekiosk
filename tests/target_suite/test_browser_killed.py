"""Target suite: the browser killed with nobody at the panel is back on the panel in time."""

import subprocess
import time

# TST001's bound
_BOUND_SECONDS = 45
# stop polling; past the bound, so the record still carries the time it took
_GIVE_UP_SECONDS = 120


def test_browser_killed(board, panel, record_property):
    """TST001 browser killed: SIGKILL the browser and time until the instance is on the panel again."""
    record_property("requirement", "TST001")
    _, before = panel.wait_on_panel()

    stdout, _stderr, _returncode = board.run(
        "cat /proc/uptime; kill -KILL $(pgrep -x surf)", check=True
    )
    killed_at = float(stdout[0].split()[0])
    give_up_at = time.monotonic() + _GIVE_UP_SECONDS

    sample = None
    seen_payload = False
    recovered_s = None
    while True:
        try:
            uptime_s, sample = panel.read()
        except subprocess.TimeoutExpired:
            uptime_s, sample = None, None
        seen_payload = seen_payload or sample is not None
        if panel.on_panel(sample) and sample["nonce"] != before["nonce"]:
            # The board uptime of the first read showing the page back, so it overstates by up
            # to one read plus the 0.5 s sleep.
            recovered_s = round(uptime_s - killed_at, 1)
            break
        if time.monotonic() > give_up_at:
            break
        time.sleep(0.5)

    record_property("before", before)
    record_property("after", sample)
    record_property("killed_at_uptime_s", killed_at)
    record_property("recovered_s", recovered_s)

    assert recovered_s is not None, (
        "no probe payload after the kill"
        if not seen_payload
        else "no sample on the panel carried a new nonce"
    )
    assert recovered_s <= _BOUND_SECONDS, (
        f"back on the panel after {recovered_s} s; TST001's bound is {_BOUND_SECONDS} s"
    )
