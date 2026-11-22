"""Target suite: a restarted, crashed or power-cut board, nobody at the panel, serves the instance in time."""

import subprocess
import time

from labgrid.driver.exception import ExecutionError

from panel import Panel
from recovery import GIVE_UP_SECONDS, assert_back_within, poll_from, until_up

# TST004's bound
_CRASH_BOUND_SECONDS = 100
# TST011's bound
_RESTART_BOUND_SECONDS = 60
# TST002's bound
_POWER_CUT_BOUND_SECONDS = 60
# TST012's bound
_COLD_BOOT_BOUND_SECONDS = 110


def _back_s(board, cmd):
    """Run `cmd`; return seconds until the instance is up (None if never) and the last read."""
    assert board.wait_for_page(), "the board did not serve the page before the fault"
    started = time.monotonic()
    board.restart_by(cmd)
    # Overstates by the boot-id read, the disconnect and the ssh connect before the fault lands.
    return until_up(board, started)


def test_kernel_crash(board, record_property):
    """TST004 kernel crash: crash the kernel and time until the page is served, browser running."""
    record_property("requirement", "TST004")
    back_s, last_read = _back_s(board, "echo c > /proc/sysrq-trigger")
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    assert_back_within(back_s, last_read, "crash", "TST004", _CRASH_BOUND_SECONDS)


def test_restart_to_the_panel(board, record_property):
    """TST011 restart to the panel: restart the board; time until the page is served, browser up."""
    record_property("requirement", "TST011")
    back_s, last_read = _back_s(board, "systemctl reboot")
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    assert_back_within(back_s, last_read, "restart", "TST011", _RESTART_BOUND_SECONDS)


def test_power_cut_while_showing(board, power_cut, record_property):
    """Cut power with the instance up; time until the page is served with the browser running."""
    record_property("requirement", "TST002")
    ready_s, last_read = until_up(board, time.monotonic())
    assert ready_s is not None, f"the instance was not up before the cut; last read: {last_read}"
    started = power_cut()
    back_s, last_read = until_up(board, started)
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    assert_back_within(back_s, last_read, "power returning", "TST002", _POWER_CUT_BOUND_SECONDS)


def _loaded_instance(titles):
    """The title of a window surf has finished loading the instance's page into, else None.

    surf titles a window `<indicators>:<indicators> | <page title>`, prefixed `[NN%] ` while the page
    loads; the instance's page title is `WiseKiosk`.
    """
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
    on_panel_s, titles = poll_from(
        started, lambda: _titles(panel), lambda t: _loaded_instance(t) is not None
    )
    record_property("on_panel_s", on_panel_s)
    record_property("last_titles", titles)
    record_property("loaded", _loaded_instance(titles) if titles else None)
    assert on_panel_s is not None, (
        f"the browser had not finished loading the instance within {GIVE_UP_SECONDS} s "
        f"of power returning; last window titles: {titles!r}"
    )
    assert on_panel_s <= _COLD_BOOT_BOUND_SECONDS, (
        f"the browser finished loading after {on_panel_s} s; TST012's bound is {_COLD_BOOT_BOUND_SECONDS} s"
    )
