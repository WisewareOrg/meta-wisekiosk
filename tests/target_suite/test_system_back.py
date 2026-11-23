"""Target suite: with nobody at the panel, the appliance's clock and its remote shell come back after a fault."""

import operator
from collections.abc import Callable

import pytest
from board import Board
from board_test import BoardTest, case

# what "back" is read as: the clock agreeing with the network's time; a remote shell opening
CLOCK_AGREES = operator.attrgetter("system.clock_agrees")
REMOTE_SHELL = operator.attrgetter("opens_a_shell")


class TestSystemBack(BoardTest):
    """With nobody at the panel, the appliance's clock and its remote shell come back after a fault."""

    @pytest.mark.parametrize(
        ("requirement", "fault", "back", "bound_s"),
        [
            case("TST015", lambda board: board.system.restart_with_clock_wrong(), CLOCK_AGREES, 100),
            case("TST029", lambda board: board.network.cut_off(seconds=60), REMOTE_SHELL, 30),
        ],
    )
    def test_back_after_a_fault(
        self,
        requirement: str,
        fault: Callable[[Board], float | Callable[[], float]],
        back: Callable[[Board], Callable[[], bool]],
        bound_s: float,
    ) -> None:
        """A fault, then the time until what it took away is back.

        Args:
            requirement: the item.
            fault: the item's stimulus; returns the instant its time counts from, or what reads it.
            back: the board's read of whether what the fault took away is back, as the item judges it.
            bound_s: the item's bound.
        """
        self.record(requirement=requirement)

        since = fault(self.board)
        back_s = self.board.seconds_until(back(self.board), since=since)

        self.record(back_s=back_s)
        assert back_s <= bound_s, f"back after {back_s} s; {requirement}'s bound is {bound_s} s"
