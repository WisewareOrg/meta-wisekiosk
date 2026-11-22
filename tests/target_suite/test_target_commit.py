"""Target suite: the booted image update names the commit it was built from."""

import pytest
from board_test import BoardTest


class TestTargetCommit(BoardTest):
    """The booted image names the commit it was built from."""

    def test_buildinfo_names_commit(self, bench_candidate: str | None) -> None:
        """TST016: after an image update, /etc/buildinfo names the installed commit.

        Args:
            bench_candidate: the commit under test, or None outside a build.
        """
        if bench_candidate is None:
            pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
        self.record(requirement="TST016")

        commit = self.board.updates.build_commit()

        assert commit == bench_candidate, f"board reports commit {commit}, expected {bench_candidate} (bench_candidate)"
