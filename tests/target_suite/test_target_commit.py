"""Target suite: the appliance runs the build an image update carried."""

from board_test import BoardTest


class TestTargetCommit(BoardTest):
    """After an image update, the appliance reports the build the update carried."""

    def test_buildinfo_names_commit(self) -> None:
        """TST016: after the start-of-run image update, the board reports the build the update carried."""
        self.record(requirement="TST016")
        installed = self.board.updates.installed

        commit = self.board.updates.build_commit()

        self.record(commit=commit)
        assert commit == installed.commit, f"the board runs {commit}, not the update's {installed.commit}"
