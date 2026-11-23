"""Target suite: an image update not meant for the board is refused, and the board runs on as it was."""

import operator
from collections.abc import Callable

import pytest
from board import Board
from board_test import BoardTest, case
from refused_offers import Offer


def _seed_offer(board: Board) -> Offer:
    """SEED: stage the candidate's own bundle in the other slot, then make the foreign-signature offer."""
    updates = board.updates
    updates.return_to_candidate_after_test(updates.bundles)
    returncode, output, _seconds = updates.install_bundle(updates.bundles.candidate, updates.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
    assert returncode == 0, f"SEED: staging the candidate returned {returncode}: {output}"
    return updates.refused_offers.foreign_signature


@pytest.mark.sends_update
class TestRefusedUpdates(BoardTest):
    """An update signed by no operator, or meant for other hardware, is refused and changes nothing."""

    @pytest.mark.parametrize(
        ("requirement", "offer"),
        [
            case("TST017", lambda board: _seed_offer(board)),
            case("TST018", operator.attrgetter("updates.refused_offers.other_hardware")),
        ],
    )
    def test_refuses_an_update(self, requirement: str, offer: Callable[[Board], Offer]) -> None:
        """Offer an update the board must refuse; it refuses it, will restart into its slot, and shows the instance.

        Args:
            requirement: the item.
            offer: the board's update the item offers.
        """
        self.record(requirement=requirement)
        self.board.app.install_probe()
        self.board.app.wait_until_on_panel()
        booted = self.board.updates.rauc_status()["booted"]

        offered = self.board.updates.offer(offer(self.board))
        next_boot = self.board.updates.next_boot_slot()
        on_panel = self.board.app.on_panel()

        self.record(install_rc=offered.returncode, booted=booted, next_boot=next_boot, on_panel=on_panel)
        assert offered.returncode == 1, (
            f"the install returned {offered.returncode}, not a refusal (1): {offered.output}"
        )
        assert next_boot == booted, f"the next restart boots slot {next_boot}, not the booted {booted}"
        assert on_panel, f"the instance is not on the panel; the probe reports {self.board.app.report()!r}"
        offered.confirm_refused_for_its_reasons()
