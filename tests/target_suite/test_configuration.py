"""Target suite: the board's own config is byte for byte the same after an image update, a restart and a power cut."""

from collections.abc import Callable

import pytest
from board import Board
from board_test import BoardTest, case


class TestConfiguration(BoardTest):
    """The board's own config survives an image update, a restart and a power cut unchanged."""

    def test_config_held_across_image_update(self) -> None:
        """TST019: the config the board held before the start-of-run image update is the one it holds after."""
        self.record(requirement="TST019")
        installed = self.board.updates.installed

        before, after = installed.config_before, installed.config_after

        self.record(config_sha256_before=before, config_sha256_after=after)
        assert after == before, f"the board holds config {after}, not the {before} it held before the update"
        installed.confirm_a_loss_would_show()

    @pytest.mark.parametrize(
        ("requirement", "fault"),
        [
            case("TST020", lambda board: board.restart()),
            case("TST021", lambda board: board.cut_power()),
        ],
    )
    def test_config_held_across_a_fault(self, requirement: str, fault: Callable[[Board], float]) -> None:
        """The config the board held before a restart or a power cut is the one it holds after.

        Args:
            requirement: the item.
            fault: the item's stimulus.
        """
        self.record(requirement=requirement)
        before = self.board.app.config.sha256()

        fault(self.board)
        after = self.board.app.config.sha256()

        self.record(config_sha256_before=before, config_sha256_after=after)
        assert after == before, f"the board holds config {after}, not the {before} it held before"
        self.board.app.config.confirm_a_loss_would_show(before)
