"""Target suite: the board's log holds a line written before an image update."""

import pytest
from board_test import BoardTest


class TestLogKept(BoardTest):
    """The board's log keeps what was written to it before an image update."""

    def test_log_kept(self, install_candidate: tuple[str, bool] | None) -> None:
        """TST028 log kept: a marker written before the start-of-run install is in the log after it.

        Args:
            install_candidate: the marker written before the start-of-run install and whether the log
                held it before the install, or None outside a build.
        """
        if install_candidate is None:
            pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
        self.record(requirement="TST028")
        marker, seen_before = install_candidate
        assert seen_before, "the marker never reached the log before the update"

        markers = self.board.system.journal.markers()

        assert markers is not None, "reading the log failed"
        assert marker in markers, "the marker is not in the log after the update"
