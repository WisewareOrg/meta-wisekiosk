"""Target suite: a board that went down, nobody at the panel, brings the instance back in time.

It restarted, crashed, lost power or started its backend late.
"""

import time

from board import Board
from board_test import BoardTest

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
# TST033's stimulus restarts userspace only, so a new boot shows as a new start of multi-user.target
_USERSPACE_BOOT_CMD = "systemctl show -p ActiveEnterTimestampMonotonic --value multi-user.target"


class TestRestartRecovery(BoardTest):
    """A board that went down is back on the panel in time."""

    def test_kernel_crash(self) -> None:
        """TST004 kernel crash: crash the kernel and time until the page is served, browser running."""
        self.record(requirement="TST004")
        self.board.wait_for_page()

        started = self.board.restart_with("echo c > /proc/sysrq-trigger")
        back_s, last_read = self.board.seconds_until_instance_up(since=started)

        self.record(back_s=back_s, last_read=last_read)
        assert back_s is not None, f"not back within {Board.GIVE_UP_SECONDS} s of the crash; last read: {last_read}"
        assert back_s <= _CRASH_BOUND_SECONDS, f"back after {back_s} s; TST004's bound is {_CRASH_BOUND_SECONDS} s"

    def test_restart_to_the_panel(self) -> None:
        """TST011 restart to the panel: restart the board; time until the page is served, browser up."""
        self.record(requirement="TST011")
        self.board.wait_for_page()

        started = self.board.restart_with("systemctl reboot")
        back_s, last_read = self.board.seconds_until_instance_up(since=started)

        self.record(back_s=back_s, last_read=last_read)
        assert back_s is not None, f"not back within {Board.GIVE_UP_SECONDS} s of the restart; last read: {last_read}"
        assert back_s <= _RESTART_BOUND_SECONDS, f"back after {back_s} s; TST011's bound is {_RESTART_BOUND_SECONDS} s"

    def test_power_cut_while_showing(self) -> None:
        """TST002 power cut while showing: cut power with the instance up.

        Times from power returning until the page is served with the browser running.
        """
        self.record(requirement="TST002")
        ready_s, last_read = self.board.seconds_until_instance_up(since=time.monotonic())
        assert ready_s is not None, f"the instance was not up before the cut; last read: {last_read}"

        on_began, on_command_s = self.board.cut_power()
        back_s, last_read = self.board.seconds_until_instance_up(since=on_began)

        self.record(power_on_command_s=on_command_s, back_s=back_s, last_read=last_read)
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
        page = self.board.app.page

        on_began, on_command_s = self.board.cut_power()
        on_panel_s, _ = page.poll(
            until=lambda read: read.instance_loaded_title is not None, within=Board.GIVE_UP_SECONDS, since=on_began
        )

        titles = page.last_read.titles if page.last_read else None
        self.record(
            power_on_command_s=on_command_s,
            on_panel_s=on_panel_s,
            last_titles=titles,
            loaded=page.last_read.instance_loaded_title if page.last_read else None,
        )
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
        reconnect, and when the test ends, before the probe's own undo restarts the browser.
        """
        self.record(requirement="TST033")
        backend = self.board.app.backend
        page = self.board.app.page
        self.board.wait_for_page()
        backend.mask()
        self.board.restart_with("systemctl soft-reboot", boot_cmd=_USERSPACE_BOOT_CMD)
        backend.unmask_and_start_after(Board.GIVE_UP_SECONDS)
        enabled, active = backend.unit_state()
        self.record(backend_enabled_after_restart=enabled, backend_active_after_restart=active)
        assert enabled == ["masked-runtime"] and active != ["active"], (
            "INVALID CHECK, not an appliance failure: the hold did not survive the soft-reboot "
            f"(is-enabled {enabled}, is-active {active})"
        )
        self.record(probe_sha256=page.install_probe(restart_browser=False))
        self.board.cleanup.callback(backend.unmask_and_wait_for_page)
        page.assert_loaded_without_backend(self.record)

        backend.unmask_and_start()
        answered_uptime_s, on_panel_s = page.time_on_panel_after_backend_answers()

        last = page.last_read
        self.record(
            backend_answered_uptime_s=answered_uptime_s,
            on_panel_s=on_panel_s,
            last_sample=last.sample if last else None,
            last_titles=page.read_titles(),
        )
        assert answered_uptime_s is not None, f"the backend did not answer within {Board.GIVE_UP_SECONDS} s"
        assert on_panel_s is not None, (
            f"the instance was not on the panel within {Board.GIVE_UP_SECONDS} s of the backend answering; "
            f"last panel read: {last!r}"
        )
        assert on_panel_s <= _LATE_BACKEND_BOUND_SECONDS, (
            f"on the panel {on_panel_s} s after the backend answered; TST033's bound is {_LATE_BACKEND_BOUND_SECONDS} s"
        )
