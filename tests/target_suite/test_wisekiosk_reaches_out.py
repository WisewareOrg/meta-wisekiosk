"""Target suite: the instance's own HTTPS fetches, proved against a replayed recording."""

import time
from typing import TYPE_CHECKING

import pytest
from board_test import BoardTest
from replay import CARDS4_LIVE

if TYPE_CHECKING:
    from wisebench.proxy import Proxy

OBSERVE_AFTER_BROWSER_START_SECONDS = 60


class TestWisekioskReachesOut(BoardTest):
    """The instance's own HTTPS fetches are answered from the recording."""

    @pytest.mark.parametrize("proxy", [str(CARDS4_LIVE / "flows.har")], indirect=True)
    def test_instance_reaches_out(self, proxy: "Proxy") -> None:
        """TST010: the instance's own HTTPS fetches are answered from the recording, none unanswered.

        Both halves are read once `OBSERVE_AFTER_BROWSER_START_SECONDS` have passed since the
        browser start.

        Args:
            proxy: the proxy replaying the cards4-live recording.
        """
        self.board.app.backend.put_behind(proxy, CARDS4_LIVE / "config.json")
        browser_started = time.monotonic()
        self.record(requirement="TST010")

        time.sleep(max(0, browser_started + OBSERVE_AFTER_BROWSER_START_SECONDS - time.monotonic()))
        served = proxy.served()
        killed = proxy.killed()

        unserved = [url for (_method, url), count in served.items() if count == 0]
        assert not unserved, f"never served from the recording: {unserved}"
        assert not killed, f"killed, not served from the recording: {killed}"
