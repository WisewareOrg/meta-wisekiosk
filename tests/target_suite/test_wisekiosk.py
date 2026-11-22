"""Target suite: the WiseKiosk instance's page, and its recovery to the panel from a backend crash."""

from board import Board
from board_test import BoardTest

# TST032's bound
_CRASH_BOUND_SECONDS = 60
# TST034's bound
_CRASH_LOAD_BOUND_SECONDS = 60
# How long TST034 holds the backend's own restart: a stimulus setting, not a bound, long enough to
# outlast a browser restart and the hold check.
_HOLD_SECONDS = 60


class TestWisekiosk(BoardTest):
    """The instance's page is served, and comes back to the panel after a backend crash."""

    def test_page_serves(self) -> None:
        """TST022: the WiseKiosk instance's page is served on the appliance."""
        returncode, output = self.board.fetch_page()

        assert returncode == 0, f"GET / failed (rc {returncode}): {output}"
        assert "<html" in output, f"GET / did not return an <html> body: {output}"
        self.record(requirement="TST022")

    def test_backend_crash(self) -> None:
        """TST032 backend crash: SIGKILL the backend; time until the instance is on the panel, backend answering.

        The backend is killed under the loaded page. Only a sample read once the backend has answered
        after the kill counts, so the page as it stood at the kill cannot pass.
        """
        backend = self.board.app.backend
        page = self.board.app.page
        self.record(probe_sha256=page.install_probe())
        self.record(requirement="TST032")
        _, before = page.wait_for_instance()
        pid_before = backend.pid()

        killed_at = backend.sigkill()
        recovery = page.time_on_panel_after_backend_kill(killed_at)

        sample = page.last_read.sample if page.last_read else None
        self.record(
            killed_at_uptime_s=killed_at,
            backend_answered_uptime_s=recovery.answered_uptime_s,
            on_panel_s=recovery.on_panel_s,
            left_panel=recovery.left_panel,
            nonce_before=before["nonce"],
            nonce_after=sample["nonce"] if sample else None,
            last_sample=sample,
            main_pid_before=pid_before,
        )
        if recovery.answered_uptime_s is not None:
            self.record(main_pid_after=backend.assert_new_process_after_kill(pid_before))
        assert recovery.on_panel_s is not None, (
            f"the instance was not on the panel with the backend answering within {Board.GIVE_UP_SECONDS} s "
            f"of the crash (backend answered at uptime {recovery.answered_uptime_s}); last sample: {sample!r}"
        )
        assert recovery.on_panel_s <= _CRASH_BOUND_SECONDS, (
            f"on the panel {recovery.on_panel_s} s after the crash; TST032's bound is {_CRASH_BOUND_SECONDS} s"
        )

    def test_backend_crash_during_browser_start(self) -> None:
        """TST034 browser start during a backend crash: restart the browser with the backend down.

        SIGKILL the backend and restart the browser while it is down; time from the backend's first
        answer again to the instance on the panel. The backend's own restart is held by a runtime
        drop-in, whose undo is registered again after the probe so it runs before the probe's own
        undo restarts the browser.
        """
        self.record(requirement="TST034")
        backend = self.board.app.backend
        page = self.board.app.page
        self.board.wait_for_page()
        backend.delay_restart(_HOLD_SECONDS)
        pid_before = backend.pid()
        killed_at = backend.sigkill()
        self.record(killed_at_uptime_s=killed_at)
        self.record(probe_sha256=page.install_probe())
        self.board.cleanup.callback(backend.undo_restart_delay)
        page.assert_loaded_without_backend(self.record)

        answered_uptime_s, on_panel_s = page.time_on_panel_after_backend_answers()

        last = page.last_read
        self.record(
            backend_answered_uptime_s=answered_uptime_s,
            backend_down_s=round(answered_uptime_s - killed_at, 1) if answered_uptime_s is not None else None,
            on_panel_s=on_panel_s,
            last_sample=last.sample if last else None,
            last_titles=page.read_titles(),
            main_pid_before=pid_before,
        )
        if answered_uptime_s is not None:
            self.record(main_pid_after=backend.assert_new_process_after_kill(pid_before))
        assert answered_uptime_s is not None, f"the backend did not answer within {Board.GIVE_UP_SECONDS} s"
        assert on_panel_s is not None, (
            f"the instance was not on the panel within {Board.GIVE_UP_SECONDS} s of the backend answering; "
            f"last panel read: {last!r}"
        )
        assert on_panel_s <= _CRASH_LOAD_BOUND_SECONDS, (
            f"on the panel {on_panel_s} s after the backend answered; TST034's bound is {_CRASH_LOAD_BOUND_SECONDS} s"
        )
