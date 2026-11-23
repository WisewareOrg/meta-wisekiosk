"""Target suite: the replayed page's motion stays within a bound of frame stalls."""

from board_test import BoardTest, replaying
from replay import CARDS4_LIVE


class TestMotion(BoardTest):
    """The replayed page's motion stays within a bound of frame stalls."""

    @replaying(CARDS4_LIVE)
    def test_motion_stutter(self) -> None:
        """TST009: over 320 s opening 40 s after the replayed page is complete, at most 24 frames of 250 ms or more."""
        self.record(requirement="TST009")
        self.board.app.run_behind_replay()
        self.board.app.install_probe()

        stalls = self.board.app.frame_stalls(cutoff_ms=250, window_s=320, after_s=40)

        self.record(stalls=stalls)
        assert stalls <= 24, f"{stalls} frame intervals of 250 ms or longer; TST009's bound is 24"
