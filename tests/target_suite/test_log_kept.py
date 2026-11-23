"""Target suite: the board's log keeps a line written before an image update."""

from board_test import BoardTest


class TestLogKept(BoardTest):
    """The board's log keeps what was written to it before an image update."""

    def test_log_kept(self) -> None:
        """TST028: a marker written to the log before the start-of-run image update is in the log after it."""
        self.record(requirement="TST028")
        marker = self.board.updates.installed.logged_marker()

        logged = self.board.system.log_markers()

        assert marker in logged, f"the marker {marker} is not among the log's markers after the update: {logged}"
