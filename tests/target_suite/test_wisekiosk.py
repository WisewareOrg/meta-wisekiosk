"""Target suite: the WiseKiosk instance's page, and its recovery to the panel from a backend crash."""

import subprocess
import time

# TST032's bound
_CRASH_BOUND_SECONDS = 60
_POLL_SECONDS = 0.5
_MAIN_PID_CMD = "systemctl show -p MainPID --value wisekiosk.service"


def test_page_serves(board, record_property):
    """The WiseKiosk instance's page is served on the appliance."""
    returncode, output = board.fetch_page()
    assert returncode == 0, f"GET / failed (rc {returncode}): {output}"
    assert "<html" in output, f"GET / did not return an <html> body: {output}"
    record_property("requirement", "TST022")


def _main_pid(board):
    """The backend's MainPID as systemd reports it."""
    return board.run(_MAIN_PID_CMD, check=True)[0][0].strip()


def test_backend_crash(board, panel, record_property):
    """TST032 backend crash: SIGKILL the backend; time until the browser shows a new load of the instance.

    Beside the pass, records whether the instance left the panel after the kill and when it was
    first on the panel again under any load.
    """
    record_property("requirement", "TST032")
    _, before = panel.wait_on_panel()
    old_pid = _main_pid(board)

    stdout, _stderr, _returncode = board.run(
        "cat /proc/uptime; systemctl kill --signal=KILL wisekiosk.service", check=True
    )
    killed_at = float(stdout[0].split()[0])
    give_up_at = time.monotonic() + _CRASH_BOUND_SECONDS

    samples = []
    left_panel = False
    back_on_panel_s = None
    on_panel_s = None
    after = None
    while time.monotonic() <= give_up_at:
        try:
            uptime_s, sample = panel.read()
        except subprocess.TimeoutExpired:
            uptime_s, sample = None, None
        if uptime_s is not None:
            since_kill_s = round(uptime_s - killed_at, 1)
            shown = panel.on_panel(sample)
            fields = (sample["state"], sample["origin"], sample["nonce"]) if sample else (None,) * 3
            samples.append((since_kill_s, *fields))
            if not shown:
                left_panel = True
            elif left_panel and back_on_panel_s is None:
                back_on_panel_s = since_kill_s
            if shown and sample["nonce"] != before["nonce"]:
                # The board uptime of the first passing read, so it overstates by up to one read.
                on_panel_s, after = since_kill_s, sample
                break
        time.sleep(_POLL_SECONDS)

    new_pid = _main_pid(board)
    record_property("killed_at_uptime_s", killed_at)
    record_property("main_pid_before", old_pid)
    record_property("main_pid_after", new_pid)
    record_property("on_panel_s", on_panel_s)
    record_property("left_panel", left_panel)
    record_property("back_on_panel_s", back_on_panel_s)
    record_property("load_before", before["load"])
    record_property("load_after", after["load"] if after else None)
    record_property("samples", samples)

    assert new_pid != old_pid, (
        f"INVALID CHECK, not an appliance failure: the backend's MainPID {old_pid} did not change, "
        "so the kill did not land"
    )
    assert on_panel_s is not None and on_panel_s <= _CRASH_BOUND_SECONDS, (
        f"the instance was not on the panel under a new page load within {_CRASH_BOUND_SECONDS} s "
        f"of the crash (left the panel: {left_panel}, back under any load at: {back_on_panel_s} s); "
        f"last sample: {samples[-1] if samples else None!r}"
    )
