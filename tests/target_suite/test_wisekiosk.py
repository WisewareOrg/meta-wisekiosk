"""Target suite: the WiseKiosk instance's page, and its recovery to the panel from a backend crash."""

import contextlib
from collections.abc import Iterator

import pytest
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


class _RecoveryWatch:
    """Reads after a backend kill: the page until the backend answers, and the panel every time.

    Attributes:
        answered_at: the board uptime of the first page served (None until then).
        left_panel: whether any panel read so far was not the instance on the panel.
    """

    answered_at: float | None
    left_panel: bool

    def __init__(self, board: Board, panel: Panel) -> None:
        """Start watching with nothing seen.

        Args:
            board: the board under test.
            panel: the probe in the browser.
        """
        self._board = board
        self._panel = panel
        self.answered_at = None
        self.left_panel = False

    def read(self) -> PanelRead:
        """Read the page until the backend has answered, then the panel; note the panel left.

        Returns:
            The panel read.
        """
        if self.answered_at is None:
            uptime, served, _output = self._board.fetch_page()
            if served:
                self.answered_at = uptime
        walk = self._panel.read()
        self.left_panel = self.left_panel or not self._panel.on_panel(walk.sample)
        return walk


class TestWisekiosk:
    """The instance's page is served, and survives a backend crash."""

    @pytest.fixture(autouse=True)
    def setup(self, board: Board, record: Record) -> Iterator[None]:
        """Keep what every test here uses, and undo what each test changed once it ends.

        Args:
            board: the board under test.
            record: the test's record.

        Yields:
            None: the test runs, then `self.cleanup` undoes its changes, last first.
        """
        self.board = board
        self.record = record
        with contextlib.ExitStack() as self.cleanup:
            yield

    def test_page_serves(self) -> None:
        """The WiseKiosk instance's page is served on the appliance."""
        self.record(requirement="TST022")

        _, served, output = self.board.fetch_page()

        assert served, f"GET / did not serve an HTML page: {output}"

    def test_backend_crash(self) -> None:
        """TST032 backend crash: SIGKILL the backend under the loaded page; time until the instance is back.

        The time runs until the instance is on the panel again with the backend answering.

        Only a sample read once the backend has answered after the kill counts, so the page as it
        stood at the kill cannot pass.
        """
        self.record(requirement="TST032")
        panel = Panel(self.board, self.cleanup, self.record)
        panel.install()
        backend = Backend(self.board, self.cleanup)
        _, before = panel.wait_on_panel()
        watch = _RecoveryWatch(self.board, panel)

        killed_at, pid_before = backend.kill()
        found_s, found = panel.wait_until(
            lambda walk: watch.answered_at is not None and panel.on_panel(walk.sample),
            Board.GIVE_UP_SECONDS,
            every=_POLL_SECONDS,
            read=watch.read,
        )

        sample = panel.last_reading.sample if panel.last_reading else None
        # The board uptime of the first passing read, so it overstates by up to one read.
        on_panel_s = round(found.uptime - killed_at, 1) if found_s is not None else None

        self.record(
            killed_at_uptime_s=killed_at,
            backend_answered_uptime_s=watch.answered_at,
            on_panel_s=on_panel_s,
            left_panel=watch.left_panel,
            nonce_before=before["nonce"],
            nonce_after=sample["nonce"] if sample else None,
            last_sample=sample,
            main_pid_before=pid_before,
        )
        if watch.answered_at is not None:
            self.record(main_pid_after=backend.assert_kill_landed())
        assert on_panel_s is not None, (
            f"the instance was not on the panel with the backend answering within {Board.GIVE_UP_SECONDS} s "
            f"of the crash (backend answered at uptime {watch.answered_at}); last sample: {sample!r}"
        )
        assert on_panel_s <= _CRASH_BOUND_SECONDS, (
            f"on the panel {on_panel_s} s after the crash; TST032's bound is {_CRASH_BOUND_SECONDS} s"
        )

    def test_backend_crash_during_browser_start(self) -> None:
        """TST034 browser start during a backend crash: SIGKILL the backend and restart the browser while it is down.

        The time runs from the backend's first answer again to the instance on the panel.

        The backend's own restart is held by a runtime drop-in, whose undo is registered again after
        the probe so it runs before the probe's own teardown restarts the browser.
        """
        self.record(requirement="TST034")
        panel = Panel(self.board, self.cleanup, self.record)
        backend = Backend(self.board, self.cleanup)
        self.board.wait_for_page()
        backend.hold(_HOLD_SECONDS)
        killed_at, pid_before = backend.kill()
        self.record(killed_at_uptime_s=killed_at)
        panel.install()
        self.cleanup.callback(backend.unhold)
        panel.assert_loaded_without_backend()

        answered_uptime_s, on_panel_s = panel.time_on_panel_after_backend_answers()

        last = panel.last_reading
        self.record(
            backend_answered_uptime_s=answered_uptime_s,
            backend_down_s=round(answered_uptime_s - killed_at, 1) if answered_uptime_s is not None else None,
            on_panel_s=on_panel_s,
            last_sample=last.sample if last else None,
            last_titles=last.titles if last else None,
            main_pid_before=pid_before,
        )
        if answered_uptime_s is not None:
            self.record(main_pid_after=backend.assert_kill_landed())
        assert answered_uptime_s is not None, f"the backend did not answer within {Board.GIVE_UP_SECONDS} s"
        assert on_panel_s is not None, (
            f"the instance was not on the panel within {Board.GIVE_UP_SECONDS} s of the backend answering; "
            f"last panel read: {last!r}"
        )
        assert on_panel_s <= _CRASH_LOAD_BOUND_SECONDS, (
            f"on the panel {on_panel_s} s after the backend answered; TST034's bound is {_CRASH_LOAD_BOUND_SECONDS} s"
        )
