"""Target suite: the board's own config file is byte for byte the same after an update, a restart and a power cut."""

import pytest
from board.app.config import LiveAndDefaultHashes
from board_test import BoardTest


class TestConfiguration(BoardTest):
    """The board's own config file survives an image update, a restart and a power cut unchanged."""

    def test_config_held_across_image_update(
        self, config_hashes_across_install: LiveAndDefaultHashes | None, bench_candidate: str | None
    ) -> None:
        """TST019: the config the board held before the candidate's image update is the one it holds after.

        Args:
            config_hashes_across_install: the live config's sha256 before and after the start-of-run install,
                and the image default's after it.
            bench_candidate: the commit under test, or None outside a build.
        """
        if bench_candidate is None:
            pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
        self.record(requirement="TST019")
        before, after, default = config_hashes_across_install

        self.board.app.config.assert_held(before, after, default, self.record)

    def test_config_held_across_restart(self) -> None:
        """TST020: the config the board held before `just kiosk-reboot` is the one it holds after."""
        config = self.board.app.config
        self.record(requirement="TST020")
        before = config.live_sha256()
        default = config.default_sha256()

        self.board.reboot()
        after = config.live_sha256()

        config.assert_held(before, after, default, self.record)

    def test_config_held_across_power_cut(self) -> None:
        """TST021: the config the board held before its power was cut is the one it holds after."""
        config = self.board.app.config
        self.record(requirement="TST021")
        before = config.live_sha256()
        default = config.default_sha256()

        self.board.cut_power(self.record)
        after = config.live_sha256()

        config.assert_held(before, after, default, self.record)
