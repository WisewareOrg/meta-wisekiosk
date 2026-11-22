"""Target suite: the WiseKiosk instance's page, and its recovery to the panel from a backend crash."""

import contextlib
from collections.abc import Callable

from backend import Backend
from board import Board
from panel import Panel, PanelRead
from record import Record

# TST032's bound
_CRASH_BOUND_SECONDS = 60
# TST034's bound
_CRASH_LOAD_BOUND_SECONDS = 60
_POLL_SECONDS = 0.5
# How long TST034 holds the backend's own restart: a stimulus setting, not a bound, long enough to
# outlast a browser restart and the hold check.
_HOLD_SECONDS = 60


def test_page_serves(board: Board, record_property: Callable[[str, object], None]) -> None:
    """The WiseKiosk instance's page is served on the appliance.

    Args:
        board: the board under test, whose page is fetched.
        record_property: records the requirement.
    """
    _, served, output = board.fetch_page()
    assert served, f"GET / did not serve an HTML page: {output}"
    record_property("requirement", "TST022")


def test_backend_crash(board: Board, backend: Backend, panel: Panel, record: Record) -> None:
    """TST032 backend crash: SIGKILL the backend under the loaded page; time until the instance is back.

    The time runs until the instance is on the panel again with the backend answering.

    Only a sample read once the backend has answered after the kill counts, so the page as it
    stood at the kill cannot pass.

    Args:
        board: the board under test, whose page is read.
        backend: killed here.
        panel: the probe in the browser, read for the instance on the panel.
        record: records the requirement and what the kill and the reads measure.
    """
    record(requirement="TST032")
    _, before = panel.wait_on_panel()
    killed_at, pid_before = backend.kill()
    answered_at = None
    left_panel = False

    def read() -> PanelRead:
        """Read the page until the backend has answered, then the panel; note the panel left.

        Returns:
            The panel read.
        """
        nonlocal answered_at, left_panel
        if answered_at is None:
            uptime, served, _output = board.fetch_page()
            if served:
                answered_at = uptime
        walk = panel.read()
        left_panel = left_panel or not panel.on_panel(walk.sample)
        return walk

    found_s, found = panel.wait_until(
        lambda walk: answered_at is not None and panel.on_panel(walk.sample),
        Board.GIVE_UP_SECONDS,
        every=_POLL_SECONDS,
        read=read,
    )
    sample = panel.last_reading.sample if panel.last_reading else None
    # The board uptime of the first passing read, so it overstates by up to one read.
    on_panel_s = round(found.uptime - killed_at, 1) if found_s is not None else None

    record(
        killed_at_uptime_s=killed_at,
        backend_answered_uptime_s=answered_at,
        on_panel_s=on_panel_s,
        left_panel=left_panel,
        nonce_before=before["nonce"],
        nonce_after=sample["nonce"] if sample else None,
        last_sample=sample,
        main_pid_before=pid_before,
    )
    if answered_at is not None:
        record(main_pid_after=backend.assert_kill_landed())
    assert on_panel_s is not None, (
        f"the instance was not on the panel with the backend answering within {Board.GIVE_UP_SECONDS} s "
        f"of the crash (backend answered at uptime {answered_at}); last sample: {sample!r}"
    )
    assert on_panel_s <= _CRASH_BOUND_SECONDS, (
        f"on the panel {on_panel_s} s after the crash; TST032's bound is {_CRASH_BOUND_SECONDS} s"
    )


def test_backend_crash_during_browser_start(
    board: Board, backend: Backend, cleanup: contextlib.ExitStack, record: Record
) -> None:
    """TST034 browser start during a backend crash: SIGKILL the backend and restart the browser while it is down.

    The time runs from the backend's first answer again to the instance on the panel.

    The backend's own restart is held by a runtime drop-in, whose undo is registered again after
    the probe so it runs before the probe's own teardown restarts the browser.

    Args:
        board: the board under test, whose page is awaited before the crash.
        backend: held and killed here.
        cleanup: the stack the panel's undos and the hold's re-registered undo go on, so the hold is
            undone before the probe's teardown.
        record: records the requirement and what the kill and the panel measure.
    """
    record(requirement="TST034")
    panel = Panel(board, cleanup, record)
    board.wait_for_page()
    backend.hold(_HOLD_SECONDS)
    killed_at, pid_before = backend.kill()
    record(killed_at_uptime_s=killed_at)

    panel.install()
    cleanup.callback(backend.unhold)

    panel.assert_loaded_without_backend()

    answered_uptime_s, on_panel_s = panel.time_on_panel_after_backend_answers()
    last = panel.last_reading
    record(
        backend_answered_uptime_s=answered_uptime_s,
        backend_down_s=round(answered_uptime_s - killed_at, 1) if answered_uptime_s is not None else None,
        on_panel_s=on_panel_s,
        last_sample=last.sample if last else None,
        last_titles=last.titles if last else None,
        main_pid_before=pid_before,
    )
    if answered_uptime_s is not None:
        record(main_pid_after=backend.assert_kill_landed())
    assert answered_uptime_s is not None, f"the backend did not answer within {Board.GIVE_UP_SECONDS} s"
    assert on_panel_s is not None, (
        f"the instance was not on the panel within {Board.GIVE_UP_SECONDS} s of the backend answering; "
        f"last panel read: {last!r}"
    )
    assert on_panel_s <= _CRASH_LOAD_BOUND_SECONDS, (
        f"on the panel {on_panel_s} s after the backend answered; TST034's bound is {_CRASH_LOAD_BOUND_SECONDS} s"
    )
