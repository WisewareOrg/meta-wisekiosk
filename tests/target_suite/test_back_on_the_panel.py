"""Target suite: with nobody at the panel, it keeps showing the WiseKiosk instance, and gets it back if it stops."""

import operator
from collections.abc import Callable
from pathlib import Path

import pytest
from board import Board
from board_test import BoardTest, case

# what "back" is read as: the instance on the panel; its page served with the browser running; the
# browser finished loading the instance's page
ON_PANEL = operator.attrgetter("app.on_panel")
UP = operator.attrgetter("app.is_up")
LOADED = operator.attrgetter("app.loaded_the_instance")
CLOCK_WITH_SECONDS = Path(__file__).resolve().parent / "clock-seconds.json"
SENDS_UPDATE = [pytest.mark.sends_update]
# TST008's load, and how long after any stop the panel has to be back
NETWORK_LOAD_SECONDS = 60
BACK_WITHIN_SECONDS = 60


class TestBackOnThePanel(BoardTest):
    """With nobody at the panel, the appliance brings the instance back after a fault or a restart."""

    @pytest.mark.parametrize(
        ("requirement", "fault", "back", "bound_s"),
        [
            case("TST001", lambda board: board.app.browser.kill(), ON_PANEL, 45),
            case("TST032", lambda board: board.app.backend.kill(), ON_PANEL, 60),
            case("TST034", lambda board: board.app.kill_backend_while_browser_starts(), ON_PANEL, 60),
            case("TST004", lambda board: board.crash_kernel(), UP, 100),
            case("TST002", lambda board: board.cut_power(), UP, 60),
            case("TST011", lambda board: board.restart(), UP, 60),
            case("TST012", lambda board: board.cut_power(), LOADED, 110),
            case("TST033", lambda board: board.app.restart_with_backend_held(), ON_PANEL, 60),
            case(
                "TST003",
                lambda board: board.updates.cut_power_while_writing(board.updates.bundles.new_build),
                UP,
                60,
                marks=SENDS_UPDATE,
            ),
        ],
    )
    def test_back_after_a_fault(
        self,
        requirement: str,
        fault: Callable[[Board], float],
        back: Callable[[Board], Callable[[], bool]],
        bound_s: float,
    ) -> None:
        """A fault or a restart with the instance on the panel, then the time until the instance is back.

        Args:
            requirement: the item.
            fault: the item's stimulus; returns the instant its time counts from.
            back: the board's read of whether the instance is back, as the item judges it.
            bound_s: the item's bound.
        """
        self.record(requirement=requirement)
        self.board.app.install_probe()
        self.board.app.wait_until_on_panel()

        since = fault(self.board)
        back_s = self.board.seconds_until(back(self.board), since=since)

        self.record(back_s=back_s)
        assert back_s <= bound_s, f"back after {back_s} s; {requirement}'s bound is {bound_s} s"

    @pytest.mark.sends_update
    def test_new_application_build(self) -> None:
        """TST006: install a different WiseKiosk build over the air; the instance is on the panel once restarted.

        The update is judged taken before the panel is timed: an update that is not taken leaves no
        restart into it to time from.
        """
        self.record(requirement="TST006")
        new_build = self.board.updates.bundles.new_build
        self.board.app.install_probe()
        self.board.app.wait_until_on_panel()

        update = self.board.updates.install_and_restart(new_build)

        self.record(install_rc=update.returncode)
        assert update.returncode == 0, f"the install returned {update.returncode}: {update.output}"
        assert update.booted_after != update.booted_before, "the board did not restart into the update"

        back_s = self.board.seconds_until(self.board.app.on_panel, since=update.restarted_at)

        self.record(back_s=back_s)
        assert back_s <= 160, f"on the panel after {back_s} s; TST006's bound is 160 s"

    def test_frozen_page_recovered(self) -> None:
        """TST005: freeze the page showing a clock with seconds, then time until the panel is changing again.

        The page is frozen only once the instance is on the panel, which the probe reports when surf has
        finished loading it: surf watches a page for answers only from then on.
        """
        self.record(requirement="TST005")
        self.board.app.install_probe()
        self.board.app.config.use(CLOCK_WITH_SECONDS)
        self.board.app.wait_until_on_panel()

        since = self.board.app.freeze_page()
        back_s = self.board.seconds_until(self.board.screen.is_changing, since=since, reads=3)

        self.record(back_s=back_s)
        assert back_s <= 60, f"changing again after {back_s} s; TST005's bound is 60 s"

    def test_sustained_network_load(self) -> None:
        """TST008: load the network; no time off the panel, through the load and after it, may pass 60 s."""
        self.record(requirement="TST008")
        self.board.app.install_probe()
        self.board.app.wait_until_on_panel()

        with self.board.network.load(seconds=NETWORK_LOAD_SECONDS) as load:
            longest_off_s = self.board.longest_lapse_s(
                self.board.app.on_panel, over=NETWORK_LOAD_SECONDS + BACK_WITHIN_SECONDS
            )

        self.record(longest_off_s=longest_off_s)
        assert longest_off_s <= BACK_WITHIN_SECONDS, (
            f"off the panel for {longest_off_s} s; TST008 allows {BACK_WITHIN_SECONDS} s"
        )
        load.confirm_applied()


class TestPanelNeverBlanks(BoardTest):
    """With nobody at the panel, the display server does not blank it."""

    def test_display_blanking_disabled(self) -> None:
        """TST007: the display server's screen saver timeout is zero and its power management is disabled."""
        self.record(requirement="TST007")

        screen_saver_timeout_s, dpms_enabled = self.board.screen.blanking()

        self.record(screen_saver_timeout_s=screen_saver_timeout_s, dpms_enabled=dpms_enabled)
        assert screen_saver_timeout_s == 0, f"the screen saver's timeout is {screen_saver_timeout_s} s"
        assert not dpms_enabled, "display power management is enabled"
