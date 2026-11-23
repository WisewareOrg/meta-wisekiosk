"""Target suite: an image update not meant for the board is refused, and the board runs on as it was."""

import operator
from collections.abc import Callable

import pytest
from board import Board
from board_test import BoardTest, case


@pytest.mark.sends_update
class TestRefusedUpdates(BoardTest):
    """An update signed by no operator, or meant for other hardware, is refused and changes nothing."""

    @pytest.mark.parametrize(
        ("requirement", "offer"),
        [
            case("TST017", operator.attrgetter("updates.refused_offers.foreign_signature")),
            case("TST018", operator.attrgetter("updates.refused_offers.other_hardware")),
        ],
    )
    def test_refuses_an_update(self, requirement: str, offer: Callable[[Board], object]) -> None:
        """Offer an update the board must refuse; it refuses it, runs the same build, and shows the instance.

        Args:
            requirement: the item.
            offer: the board's update the item offers.
        """
        self.record(requirement=requirement)
        self.board.app.install_probe()
        self.board.app.wait_until_on_panel()
        build = self.board.updates.build_commit()

        refused = self.board.updates.refuses(offer(self.board))
        build_after = self.board.updates.build_commit()
        on_panel = self.board.app.on_panel()

        self.record(refused=refused, build=build_after, on_panel=on_panel)
        assert refused, "the board did not refuse the update"
        assert build_after == build, f"the board runs {build_after}, not the {build} it ran before"
        assert on_panel, "the instance is not on the panel"
