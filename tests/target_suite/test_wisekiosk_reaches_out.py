"""Target suite: the instance's own HTTPS fetches, answered from a replayed recording."""

import time

from board_test import BoardTest, replaying
from replay import CARDS4_LIVE

# how long the instance is let fetch its data, from the browser's start
FETCH_SECONDS = 60


class TestWisekioskReachesOut(BoardTest):
    """The instance's own HTTPS fetches are answered from the recording."""

    @replaying(CARDS4_LIVE)
    def test_instance_reaches_out(self) -> None:
        """TST010: start the instance behind the replay; each recorded request is answered, and none goes unanswered."""
        self.record(requirement="TST010")

        replay = self.board.app.run_behind_replay()
        time.sleep(FETCH_SECONDS)
        never_answered = [url for (_method, url), count in replay.served().items() if count == 0]
        unanswered = replay.killed()

        self.record(never_answered=never_answered, unanswered=unanswered)
        assert not never_answered, f"never answered from the recording: {never_answered}"
        assert not unanswered, f"the instance's requests the recording did not answer: {unanswered}"
