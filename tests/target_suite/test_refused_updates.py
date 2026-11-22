"""Target suite: an image update not meant for the board is refused, and the board is left as it was."""

import pytest
from board_test import BoardTest
from refused_offers import RefusedOffers

# only catches a hang, with the install tool's own checks and bundle server included;
# neither TST017 nor TST018 states a bound
_INSTALL_TIMEOUT_SECONDS = 120


@pytest.mark.sends_update
class TestRefusedUpdates(BoardTest):
    """An update signed by no operator, or meant for other hardware, is refused and changes nothing."""

    def setup_method(self) -> None:
        """Put the probe in the browser."""
        self.record(probe_sha256=self.board.app.page.install_probe())

    def test_foreign_signature(self, refused_offers: RefusedOffers) -> None:
        """TST017 foreign signature: offer an update signed by a key no operator holds; it is refused.

        Args:
            refused_offers: the run's refused bundles.
        """
        self.record(requirement="TST017")

        self.board.updates.assert_refused(
            refused_offers.foreign_signature,
            ("signature verification failed", "self-signed certificate"),
            _INSTALL_TIMEOUT_SECONDS,
            self.record,
        )

    def test_another_hardware_type(self, refused_offers: RefusedOffers) -> None:
        """TST018 another hardware type: offer an operator-signed update for other hardware; it is refused.

        Args:
            refused_offers: the run's refused bundles.
        """
        self.record(requirement="TST018")

        self.board.updates.assert_refused(
            refused_offers.other_hardware,
            ("Compatible mismatch", refused_offers.other_hardware_compatible),
            _INSTALL_TIMEOUT_SECONDS,
            self.record,
        )
