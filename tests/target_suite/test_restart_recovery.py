"""Target suite: a restarted, crashed or power-cut board, nobody at the panel, serves the instance in time."""

import subprocess
import time

from labgrid.driver.exception import ExecutionError

from panel import OWN_ORIGINS, Panel

# TST004's bound
_CRASH_BOUND_SECONDS = 100
# TST011's bound
_RESTART_BOUND_SECONDS = 60
# TST002's and TST003's bound
_POWER_CUT_BOUND_SECONDS = 60
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


def _until_up(board, started):
    """Poll from `started` until the instance is up; return seconds (None if never) and the last read."""
    while True:
        last_read = _instance_up(board)
        if all(last_read):
            return round(time.monotonic() - started, 1), last_read
        if time.monotonic() - started > _GIVE_UP_SECONDS:
            return None, last_read
        time.sleep(1)


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
    """TST002 power cut while showing: cut power with the instance up; time until it is served again."""
    record_property("requirement", "TST002")
    assert all(_instance_up(board)), "the instance was not up before the cut"
    started = power_cut()
    back_s, last_read = _until_up(board, started)
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    _check(back_s, last_read, "power returning", "TST002", _POWER_CUT_BOUND_SECONDS)


def _loaded_instance(board, titles):
    """The matched title and browser URL when surf has finished loading the instance's own page, else None."""
    title = next((t for t in titles if t.endswith(" | WiseKiosk") and not t.startswith("[")), None)
    if title is None:
        return None
    stdout, _stderr, returncode = board.run("tr '\\0' ' ' < /proc/$(pgrep -x surf)/cmdline")
    cmdline = " ".join(stdout)
    if returncode != 0 or not any(origin in cmdline for origin in OWN_ORIGINS):
        return None
    return title, cmdline


def test_cold_boot_to_the_panel(board, power_cut, record_property):
    """TST012 cold boot to the panel: cut power; time until surf has loaded the instance's own page."""
    record_property("requirement", "TST012")
    panel = Panel(board)
    started = power_cut()
    while True:
        try:
            _uptime_s, titles = panel.titles()
            loaded = _loaded_instance(board, titles)
        except (subprocess.TimeoutExpired, ExecutionError):
            titles, loaded = [], None
        if loaded is not None:
            on_panel_s = round(time.monotonic() - started, 1)
            break
        if time.monotonic() - started > _GIVE_UP_SECONDS:
            on_panel_s = None
            break
        time.sleep(1)
    record_property("on_panel_s", on_panel_s)
    record_property("last_titles", titles)
    record_property("loaded", loaded)
    assert on_panel_s is not None, (
        f"the browser had not finished loading the instance within {_GIVE_UP_SECONDS} s "
        f"of power returning; last window titles: {titles!r}"
    )
