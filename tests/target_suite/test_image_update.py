"""Target suite: image updates the board falls back from, each starting and ending with the board on the candidate.

The bundles are copies of the candidate, edited and re-signed by the operator key. Each carries an
install-check hook that refuses unless this run's nonce is in the board's `/tmp`.
"""

import pytest
from board_test import BoardTest
from candidate_bundles import CandidateBundles


@pytest.mark.sends_update
class TestImageUpdate(BoardTest):
    """An update that cannot start, or cannot join the network, is fallen back from."""

    def test_cannot_start(self, candidate_bundles: CandidateBundles) -> None:
        """TST023 cannot start: install an update that cannot start; the board falls back, then takes a valid update.

        The fallback alone does not show why the update could not start; update_bundles.sh's
        `require_gone` checks are what show the bundle lacks init and sh.

        Args:
            candidate_bundles: this run's test bundles, and the candidate they were made from.
        """
        self.board.updates.return_to_candidate_after_test(candidate_bundles)
        self.record(requirement="TST023")

        self.board.updates.assert_falls_back_then_takes_candidate(
            candidate_bundles.cannot_start, candidate_bundles, count_boots=False, record=self.record
        )

    def test_cannot_reach_the_network(self, candidate_bundles: CandidateBundles) -> None:
        """TST024 cannot reach the network: install an update that starts but cannot join; the board falls back.

        Args:
            candidate_bundles: this run's test bundles, and the candidate they were made from.
        """
        self.board.updates.return_to_candidate_after_test(candidate_bundles)
        self.record(requirement="TST024")

        self.board.updates.assert_falls_back_then_takes_candidate(
            candidate_bundles.no_network, candidate_bundles, count_boots=True, record=self.record
        )
