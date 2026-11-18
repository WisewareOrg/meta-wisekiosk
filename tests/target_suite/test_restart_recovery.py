"""Target suite: a restarted, crashed or power-cut board, nobody at the panel, serves the instance in time."""

import subprocess
import time

from labgrid.driver.exception import ExecutionError

from panel import Panel

# TST004's bound
_CRASH_BOUND_SECONDS = 100
# TST011's bound
_RESTART_BOUND_SECONDS = 60
# TST002's bound
_POWER_CUT_BOUND_SECONDS = 60
# TST012's bound
_COLD_BOOT_BOUND_SECONDS = 110
# stop polling; past the bound, so the record still carries the time it took
_GIVE_UP_SECONDS = 180


def _instance_up(board):
    """Read whether the browser is running and whether the page is served, as a pair."""
    try:
        _, _, browser = board.run("pgrep -x surf")
    except (ExecutionError, subprocess.TimeoutExpired):
        browser = None
    try:
        page_served = board.page_served()
    except ExecutionError:
        page_served = False
    return browser == 0, page_served


def _poll_from(started, read, done):
    """Poll `read` once a second from `started` until `done(value)`; return seconds and the last value.

    Seconds is None when `_GIVE_UP_SECONDS` passed first. A read returning None is a failed read:
    it does not replace the last value. The power-cut callers start at `power_cut()`'s return, so
    they overstate by at most one read plus the 1 s sleep.
    """
    last = None
    while True:
        value = read()
        if value is not None:
            last = value
        if value is not None and done(value):
            return round(time.monotonic() - started, 1), last
        if time.monotonic() - started > _GIVE_UP_SECONDS:
            return None, last
        time.sleep(1)


def _until_up(board, started):
    """Poll from `started` until the instance is up; return seconds (None if never) and the last read."""
    return _poll_from(started, lambda: _instance_up(board), all)


def _back_s(board, cmd):
    """Run `cmd`; return seconds until the instance is up (None if never) and the last read."""
    assert board.wait_for_page(), "the board did not serve the page before the fault"
    started = time.monotonic()
    board.restart_by(cmd)
    # Overstates by the boot-id read, the disconnect and the ssh connect before the fault
    # lands, plus up to one read and the 1 s sleep.
    return _until_up(board, started)


def _check(back_s, last_read, fault, requirement, bound):
    """Assert the instance was back, and within the bound."""
    assert back_s is not None, (
        f"the board did not serve the page with the browser running within {_GIVE_UP_SECONDS} s "
        f"of the {fault}; last read: browser running {last_read[0]}, page served {last_read[1]}"
    )
    assert back_s <= bound, (
        f"back after {back_s} s; {requirement}'s bound is {bound} s"
    )


def test_kernel_crash(board, record_property):
    """TST004 kernel crash: crash the kernel and time until the page is served, browser running."""
    record_property("requirement", "TST004")
    back_s, last_read = _back_s(board, "echo c > /proc/sysrq-trigger")
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    _check(back_s, last_read, "crash", "TST004", _CRASH_BOUND_SECONDS)


def test_restart_to_the_panel(board, record_property):
    """TST011 restart to the panel: restart the board; time until the page is served, browser up."""
    record_property("requirement", "TST011")
    back_s, last_read = _back_s(board, "systemctl reboot")
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    _check(back_s, last_read, "restart", "TST011", _RESTART_BOUND_SECONDS)


def test_power_cut_while_showing(board, power_cut, record_property):
    """Cut power with the instance up; time until the page is served with the browser running."""
    record_property("requirement", "TST002")
    ready_s, read = _until_up(board, time.monotonic())
    assert ready_s is not None, f"the instance was not up before the cut; last read: {read}"
    started = power_cut()
    back_s, last_read = _until_up(board, started)
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    _check(back_s, last_read, "power returning", "TST002", _POWER_CUT_BOUND_SECONDS)


def _loaded_instance(titles):
    """The title of a window surf has finished loading the instance's page into, else None."""
    return next((t for t in titles if t.endswith(" | WiseKiosk") and not t.startswith("[")), None)


def _titles(panel):
    """The window titles, or None when the read failed."""
    try:
        return panel.titles()
    except (subprocess.TimeoutExpired, ExecutionError):
        return None


def test_cold_boot_to_the_panel(board, power_cut, record_property):
    """Cut power; time until the browser has finished loading the instance's page."""
    record_property("requirement", "TST012")
    panel = Panel(board)
    started = power_cut()
    on_panel_s, titles = _poll_from(
        started, lambda: _titles(panel), lambda t: _loaded_instance(t) is not None
    )
    record_property("on_panel_s", on_panel_s)
    record_property("last_titles", titles)
    record_property("loaded", _loaded_instance(titles) if titles else None)
    assert on_panel_s is not None, (
        f"the browser had not finished loading the instance within {_GIVE_UP_SECONDS} s "
        f"of power returning; last window titles: {titles!r}"
    )
    assert on_panel_s <= _COLD_BOOT_BOUND_SECONDS, (
        f"the browser finished loading after {on_panel_s} s; TST012's bound is {_COLD_BOOT_BOUND_SECONDS} s"
    )
