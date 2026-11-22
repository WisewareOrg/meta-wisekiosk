"""Target suite: a board that went down, nobody at the panel, brings the instance back in time.

It restarted, crashed, lost power or started its backend late.
"""

import time

import pytest
from backend import Backend
from board import Board, Up
from panel import Panel
from record import Record

# TST004's bound
_CRASH_BOUND_SECONDS = 100
# TST011's bound
_RESTART_BOUND_SECONDS = 60
# TST002's bound
_POWER_CUT_BOUND_SECONDS = 60
# TST012's bound
_COLD_BOOT_BOUND_SECONDS = 110
# TST033's bound
_LATE_BACKEND_BOUND_SECONDS = 60

_USERSPACE_BOOT_CMD = "systemctl show -p ActiveEnterTimestampMonotonic --value multi-user.target"


def _loaded(titles: list[str]) -> str | None:
    """The title of a window surf has finished loading the instance's page into.

    surf titles a window `<indicators>:<indicators> | <page title>`, prefixed `[NN%] ` while the page
    loads; the instance's page title is `WiseKiosk`.

    Args:
        titles: every window's title.

    Returns:
        The title, or None if there is none.
    """
    return next((t for t in titles if t.endswith(" | WiseKiosk") and not t.startswith("[")), None)


class TestRestartRecovery:
    """A board that went down is back on the panel in time."""

    @pytest.fixture(autouse=True)
    def setup(self, board: Board, record: Record, request: pytest.FixtureRequest) -> None:
        """Keep what every test here uses.

        Args:
            board: the board under test.
            record: the test's record.
            request: the test's request; objects a test builds register their undos on it, and
                fixtures only some tests need are fetched through it.
        """
        self.board = board
        self.record = record
        self.request = request

    def _time_back_after(self, cmd: str) -> tuple[float | None, Up | None]:
        """Run `cmd` on the board and time until the instance is up.

        Overstates by the boot-id read, the disconnect and the ssh connect before the fault lands.

        Args:
            cmd: the command that restarts or crashes the board.

        Returns:
            The seconds until the instance is up (None if never), and the last read of it.
        """
        self.board.wait_for_page()
        started = time.monotonic()
        self.board.restart_by(cmd)
        return self.board.time_until_up(started)

    def _cut_power(self) -> float:
        """Cut the board's power and bring it back; return the host time the power came back.

        The `power_cut` fixture is fetched here, not in setup, so a test that does not cut power
        never fetches the plug's driver or switches it on at teardown.

        Returns:
            The host `time.monotonic()` at which the power-on command started.
        """
        return self.request.getfixturevalue("power_cut")()

    def test_kernel_crash(self) -> None:
        """TST004 kernel crash: crash the kernel and time until the page is served, browser running."""
        self.record(requirement="TST004")
        back_s, last_read = self._time_back_after("echo c > /proc/sysrq-trigger")
        self.record(back_s=back_s, last_read=last_read)
        assert back_s is not None, f"not back within {Board.GIVE_UP_SECONDS} s of the crash; last read: {last_read}"
        assert back_s <= _CRASH_BOUND_SECONDS, f"back after {back_s} s; TST004's bound is {_CRASH_BOUND_SECONDS} s"

    def test_restart_to_the_panel(self) -> None:
        """TST011 restart to the panel: restart the board; time until the page is served, browser up."""
        self.record(requirement="TST011")
        back_s, last_read = self._time_back_after("systemctl reboot")
        self.record(back_s=back_s, last_read=last_read)
        assert back_s is not None, f"not back within {Board.GIVE_UP_SECONDS} s of the restart; last read: {last_read}"
        assert back_s <= _RESTART_BOUND_SECONDS, f"back after {back_s} s; TST011's bound is {_RESTART_BOUND_SECONDS} s"

    def test_power_cut_while_showing(self) -> None:
        """TST002 power cut while showing: cut power with the instance up.

        Times from power returning until the page is served with the browser running.
        """
        self.record(requirement="TST002")
        ready_s, last_read = self.board.time_until_up(time.monotonic())
        assert ready_s is not None, f"the instance was not up before the cut; last read: {last_read}"
        started = self._cut_power()
        back_s, last_read = self.board.time_until_up(started)
        self.record(back_s=back_s, last_read=last_read)
        assert back_s is not None, (
            f"not back within {Board.GIVE_UP_SECONDS} s of power returning; last read: {last_read}"
        )
        assert back_s <= _POWER_CUT_BOUND_SECONDS, (
            f"back after {back_s} s; TST002's bound is {_POWER_CUT_BOUND_SECONDS} s"
        )

    def test_cold_boot_to_the_panel(self) -> None:
        """TST012 cold boot to the panel: cut power.

        Times from power returning until the browser has finished loading the instance's page.
        """
        self.record(requirement="TST012")
        panel = Panel(self.board, self.request, self.record)
        started = self._cut_power()
        on_panel_s, _ = panel.wait_until(lambda read: _loaded(read.titles), Board.GIVE_UP_SECONDS, since=started)
        titles = panel.last_reading.titles if panel.last_reading else None
        self.record(on_panel_s=on_panel_s, last_titles=titles, loaded=_loaded(titles) if titles else None)
        assert on_panel_s is not None, (
            f"the browser had not finished loading the instance within {Board.GIVE_UP_SECONDS} s "
            f"of power returning; last window titles: {titles!r}"
        )
        assert on_panel_s <= _COLD_BOOT_BOUND_SECONDS, (
            f"the browser finished loading after {on_panel_s} s; TST012's bound is {_COLD_BOOT_BOUND_SECONDS} s"
        )

    def test_backend_late_at_boot(self) -> None:
        """TST033 backend late at boot: time from the held backend's first answer to the instance on the panel.

        The backend is masked across a soft-reboot and released three ways, each idempotent: by the
        test once the browser has finished a load without it, by a board-side timer armed on
        reconnect, and at teardown before the probe's own teardown restarts the browser.
        """
        self.record(requirement="TST033")
        panel = Panel(self.board, self.request, self.record)
        backend = Backend(self.board, self.request)
        self.board.wait_for_page()

        backend.mask()
        self.board.restart_by("systemctl soft-reboot", boot_cmd=_USERSPACE_BOOT_CMD)
        backend.release_after(Board.GIVE_UP_SECONDS)

        enabled = self.board.run("systemctl is-enabled wisekiosk.service")[0]
        active = self.board.run("systemctl is-active wisekiosk.service")[0]
        self.record(backend_enabled_after_restart=enabled, backend_active_after_restart=active)
        assert enabled == ["masked-runtime"] and active != ["active"], (
            "INVALID CHECK, not an appliance failure: the hold did not survive the soft-reboot "
            f"(is-enabled {enabled}, is-active {active})"
        )

        panel.install(restart_browser=False)
        self.request.addfinalizer(backend.unmask)

        panel.assert_loaded_without_backend()

        backend.release()
        answered_uptime_s, on_panel_s = panel.time_on_panel_after_backend_answers()
        last = panel.last_reading
        self.record(
            backend_answered_uptime_s=answered_uptime_s,
            on_panel_s=on_panel_s,
            last_sample=last.sample if last else None,
            last_titles=last.titles if last else None,
        )
        assert answered_uptime_s is not None, f"the backend did not answer within {Board.GIVE_UP_SECONDS} s"
        assert on_panel_s is not None, (
            f"the instance was not on the panel within {Board.GIVE_UP_SECONDS} s of the backend answering; "
            f"last panel read: {last!r}"
        )
        assert on_panel_s <= _LATE_BACKEND_BOUND_SECONDS, (
            f"on the panel {on_panel_s} s after the backend answered; TST033's bound is {_LATE_BACKEND_BOUND_SECONDS} s"
        )
