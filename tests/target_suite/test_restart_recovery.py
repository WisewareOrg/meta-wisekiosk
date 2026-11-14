"""Target suite: a restarted or crashed board, nobody at the panel, serves the instance in time."""

import subprocess
import time

# TST004's and TST011's bound
_BOUND_SECONDS = 60
# stop polling; past the bound, so the record still carries the time it took
_GIVE_UP_SECONDS = 180


def _instance_up(board):
    """Read whether the browser is running and whether the page is served, as a pair."""
    try:
        _, _, browser = board.run("pgrep -x surf")
        returncode, output = board.fetch_page()
    except subprocess.TimeoutExpired:
        return False, False
    return browser == 0, returncode == 0 and "<html" in output


def _back_s(board, cmd):
    """Run `cmd`; return seconds until the instance is up (None past the give-up) and the last read."""
    assert board.wait_for_page(), "the board did not serve the page before the fault"
    started = time.monotonic()
    board.restart_by(cmd)
    while True:
        last_read = _instance_up(board)
        if all(last_read):
            # Overstates by up to one read plus the 1 s sleep.
            return round(time.monotonic() - started, 1), last_read
        if time.monotonic() - started > _GIVE_UP_SECONDS:
            return None, last_read
        time.sleep(1)


def _check(back_s, last_read, fault, requirement):
    """Assert the instance was back, and within the bound."""
    assert back_s is not None, (
        f"the board did not serve the page with the browser running within {_GIVE_UP_SECONDS} s "
        f"of the {fault}; last read: browser running {last_read[0]}, page served {last_read[1]}"
    )
    assert back_s <= _BOUND_SECONDS, (
        f"back after {back_s} s; {requirement}'s bound is {_BOUND_SECONDS} s"
    )


def test_kernel_crash(board, record_property):
    """TST004 kernel crash: crash the kernel and time until the page is served, browser running."""
    record_property("requirement", "TST004")
    back_s = _back_s(board, "sync; echo c > /proc/sysrq-trigger")
    record_property("back_s", back_s)
    assert back_s is not None, (
        f"the board did not serve the page with the browser running within {_GIVE_UP_SECONDS} s "
        "of the crash"
    )
    assert back_s <= _BOUND_SECONDS, (
        f"back after {back_s} s; TST004's bound is {_BOUND_SECONDS} s"
    )


def test_restart_to_the_panel(board, record_property):
    """TST011 restart to the panel: restart the board and time until the page is served, browser up."""
    record_property("requirement", "TST011")
    back_s = _back_s(board, "systemctl reboot")
    record_property("back_s", back_s)
    assert back_s is not None, (
        f"the board did not serve the page with the browser running within {_GIVE_UP_SECONDS} s "
        "of the restart"
    )
    assert back_s <= _BOUND_SECONDS, (
        f"back after {back_s} s; TST011's bound is {_BOUND_SECONDS} s"
    )
