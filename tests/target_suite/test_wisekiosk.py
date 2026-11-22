"""Target suite: the WiseKiosk instance's page, and its recovery to the panel from a backend crash."""

from collections.abc import Callable

import pytest
from backend import Backend
from board import Board
from panel import Panel

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

    Raises:
        AssertionError: the page did not serve an HTML document.
    """
    _, served, output = board.page()
    assert served, f"GET / did not serve an HTML page: {output}"
    record_property("requirement", "TST022")


def test_backend_crash(
    board: Board, backend: Backend, panel: Panel, record_property: Callable[[str, object], None]
) -> None:
    """TST032 backend crash: SIGKILL the backend under the loaded page; time until the instance is on
    the panel again with the backend answering.

    Only a sample read once the backend has answered after the kill counts, so the page as it
    stood at the kill cannot pass.

    Args:
        board: the board under test, whose page is read.
        backend: killed here.
        panel: the probe in the browser, read for the instance on the panel.
        record_property: records the requirement and what the kill and the reads measure.

    Raises:
        AssertionError: the instance was not on the panel with the backend answering within
            `Board.GIVE_UP_SECONDS`, or after the bound, or the kill did not land (INVALID CHECK).
    """
    record_property("requirement", "TST032")
    _, before = panel.wait_on_panel()
    killed_at = backend.kill()
    answered_at = None
    left_panel = False

    def read() -> tuple[float, dict[str, str] | None, list[str]] | None:
        """Read the page until the backend has answered, then the panel; note the panel left.

        Returns:
            The panel read, or None while the backend has not answered.
        """
        nonlocal answered_at, left_panel
        if answered_at is None:
            uptime, served, _output = board.page()
            if served:
                answered_at = uptime
        walk = panel.read()
        left_panel = left_panel or not panel.on_panel(walk[1])
        return walk

    found_s, last = board.wait(
        read,
        lambda walk: answered_at is not None and panel.on_panel(walk[1]),
        Board.GIVE_UP_SECONDS,
        every=_POLL_SECONDS,
    )
    sample = last[1] if last else None
    # The board uptime of the first passing read, so it overstates by up to one read.
    on_panel_s = round(last[0] - killed_at, 1) if found_s is not None else None

    record_property("backend_answered_uptime_s", answered_at)
    record_property("on_panel_s", on_panel_s)
    record_property("left_panel", left_panel)
    record_property("nonce_before", before["nonce"])
    record_property("nonce_after", sample["nonce"] if sample else None)
    record_property("last_sample", sample)
    if answered_at is not None:
        backend.assert_kill_landed()
    assert on_panel_s is not None, (
        f"the instance was not on the panel with the backend answering within {Board.GIVE_UP_SECONDS} s "
        f"of the crash (backend answered at uptime {answered_at}); last sample: {sample!r}"
    )
    assert on_panel_s <= _CRASH_BOUND_SECONDS, (
        f"on the panel {on_panel_s} s after the crash; bound {_CRASH_BOUND_SECONDS} s"
    )


def test_backend_crash_during_browser_start(
    board: Board,
    backend: Backend,
    request: pytest.FixtureRequest,
    record_property: Callable[[str, object], None],
) -> None:
    """TST034 browser start during a backend crash: SIGKILL the backend and restart the browser while
    it is down; time from the backend's first answer again to the instance on the panel.

    The backend's own restart is held by a runtime drop-in, whose undo is registered again after
    the probe so it runs before the probe's own teardown restarts the browser.

    Args:
        board: the board under test, whose page is awaited before the crash.
        backend: held and killed here.
        request: the test's request, on which the hold's undo is registered again so it runs
            before the probe's teardown.
        record_property: records the requirement and what the kill and the panel measure.

    Raises:
        AssertionError: the kill did not land or the browser never finished a load without the
            backend (INVALID CHECK), or the instance was not on the panel in time.
    """
    record_property("requirement", "TST034")
    panel = Panel(board, request, record_property)
    board.wait_for_page()
    backend.hold(_HOLD_SECONDS)
    killed_at = backend.kill()

    panel.install()
    request.addfinalizer(backend.unhold)

    panel.held()

    t0 = panel.after_answer()
    record_property("backend_down_s", round(t0 - killed_at, 1) if t0 is not None else None)
    if t0 is not None:
        backend.assert_kill_landed()
    panel.assert_on_panel_within(_CRASH_LOAD_BOUND_SECONDS)
