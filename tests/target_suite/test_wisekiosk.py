"""Target suite: the WiseKiosk instance's page, and its recovery to the panel from a backend crash."""

import time

from backend import assert_kill_landed, hold_restart, kill_backend
from panel import Panel
from recovery import (
    GIVE_UP_SECONDS,
    assert_on_panel_within,
    check_held,
    or_none,
    panel_after_answer,
    uptime_and_served,
)

# TST032's bound
_CRASH_BOUND_SECONDS = 60
# TST034's bound
_CRASH_LOAD_BOUND_SECONDS = 60
_POLL_SECONDS = 0.5
# How long TST034 holds the backend's own restart: a stimulus setting, not a bound, long enough to
# outlast a browser restart and the hold check.
_HOLD_SECONDS = 60


def test_page_serves(board, record_property):
    """The WiseKiosk instance's page is served on the appliance."""
    _, served, output = board.page()
    assert served, f"GET / did not serve an HTML page: {output}"
    record_property("requirement", "TST022")


def test_backend_crash(board, panel, record_property):
    """TST032 backend crash: SIGKILL the backend under the loaded page; time until the instance is on
    the panel again with the backend answering.

    Only a sample read once the backend has answered after the kill counts, so the page as it
    stood at the kill cannot pass.
    """
    record_property("requirement", "TST032")
    _, before = panel.wait_on_panel()
    killed_at, old_pid = kill_backend(board)
    give_up_at = time.monotonic() + GIVE_UP_SECONDS

    answered_at = None
    left_panel = False
    on_panel_s = None
    sample = None
    while time.monotonic() <= give_up_at:
        if answered_at is None:
            served = or_none(lambda: uptime_and_served(board))
            if served and served[1]:
                answered_at = served[0]
        read = or_none(panel.read)
        if read is not None:
            uptime_s, sample = read
            shown = panel.on_panel(sample)
            left_panel = left_panel or not shown
            if shown and answered_at is not None:
                # The board uptime of the first passing read, so it overstates by up to one read.
                on_panel_s = round(uptime_s - killed_at, 1)
                break
        time.sleep(_POLL_SECONDS)

    record_property("killed_at_uptime_s", killed_at)
    record_property("backend_answered_uptime_s", answered_at)
    record_property("on_panel_s", on_panel_s)
    record_property("left_panel", left_panel)
    record_property("nonce_before", before["nonce"])
    record_property("nonce_after", sample["nonce"] if sample else None)
    record_property("last_sample", sample)
    record_property("main_pid_before", old_pid)
    if answered_at is not None:
        record_property("main_pid_after", assert_kill_landed(board, old_pid))
    assert on_panel_s is not None, (
        f"the instance was not on the panel with the backend answering within {GIVE_UP_SECONDS} s "
        f"of the crash (backend answered at uptime {answered_at}); last sample: {sample!r}"
    )
    assert on_panel_s <= _CRASH_BOUND_SECONDS, (
        f"on the panel {on_panel_s} s after the crash; TST032's bound is {_CRASH_BOUND_SECONDS} s"
    )


def test_backend_crash_during_browser_start(board, request, record_property):
    """TST034 browser start during a backend crash: SIGKILL the backend and restart the browser while
    it is down; time from the backend's first answer again to the instance on the panel.

    The backend's own restart is held by a runtime drop-in, whose undo is registered again after
    the probe so it runs before the probe's own teardown restarts the browser.
    """
    record_property("requirement", "TST034")
    panel = Panel(board)
    board.wait_for_page()
    unhold = hold_restart(board, request, _HOLD_SECONDS)
    killed_at, old_pid = kill_backend(board)
    record_property("killed_at_uptime_s", killed_at)

    record_property("probe_sha256", panel.install(request))
    request.addfinalizer(unhold)

    check_held(board, panel, record_property)

    t0, on_panel_s, last = panel_after_answer(board, panel)
    record_property("backend_answered_uptime_s", t0)
    record_property("backend_down_s", round(t0 - killed_at, 1) if t0 is not None else None)
    record_property("on_panel_s", on_panel_s)
    record_property("last_sample", last[1] if last else None)
    record_property("last_titles", or_none(panel.titles))
    record_property("main_pid_before", old_pid)
    if t0 is not None:
        record_property("main_pid_after", assert_kill_landed(board, old_pid))
    assert_on_panel_within(t0, on_panel_s, last, "TST034", _CRASH_LOAD_BOUND_SECONDS)
