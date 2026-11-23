"""Target suite: image updates the board falls back from, each starting and ending with the board on the candidate.

The bundles are copies of the candidate, edited and re-signed by the operator key. Each carries an
install-check hook that refuses unless this run's nonce is in the board's `/tmp`.
"""

import operator
from collections.abc import Callable
from pathlib import Path

import pytest
from board import Board
from board_test import BoardTest, case


@pytest.mark.sends_update
class TestImageUpdate(BoardTest):
    """An update that cannot start, or cannot join the network, is fallen back from."""

    @pytest.mark.parametrize(
        ("requirement", "update", "starts"),
        [
            case("TST023", operator.attrgetter("updates.bundles.cannot_start"), False),
            case("TST024", operator.attrgetter("updates.bundles.no_network"), True),
        ],
    )
    def test_falls_back(self, requirement: str, update: Callable[[Board], Path], starts: bool) -> None:
        """Install an update that fails; the board falls back to its previous build, then takes a valid update.

        That the cannot-start update could not start is shown when it is built: update_bundles.sh's
        `require_gone` checks that it lacks init and sh.

        Args:
            requirement: the item.
            update: the board's update the item installs.
            starts: whether the update starts before it fails.
        """
        self.record(requirement=requirement)
        bundles = self.board.updates.bundles
        previous = self.board.updates.running_bundle()

        failed_attempts = self.board.updates.install_and_fall_back(update(self.board), starts=starts)
        fell_back_to = self.board.updates.running_bundle()
        valid = self.board.updates.install_and_restart(bundles.candidate)

        self.record(failed_attempts=failed_attempts, fell_back_to=fell_back_to, valid_install_rc=valid.returncode)
        assert failed_attempts <= 3, f"{failed_attempts} failed attempts to start the update; the bound is 3"
        assert fell_back_to == previous, f"the board runs bundle {fell_back_to}, not its previous {previous}"
        assert valid.returncode == 0, f"the valid update's install returned {valid.returncode}: {valid.output}"
        assert valid.booted_after != valid.booted_before, "the board did not restart into the valid update"
