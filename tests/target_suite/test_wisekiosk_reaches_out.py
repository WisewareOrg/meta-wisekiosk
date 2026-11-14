"""Target suite: the instance's own HTTPS fetches, proved against a replayed recording."""

import time

import pytest

from replay import CARDS4_LIVE

OBSERVE_AFTER_BROWSER_START_SECONDS = 60


@pytest.mark.parametrize("proxy", [str(CARDS4_LIVE / "flows.har")], indirect=True)
def test_instance_reaches_out(proxy, replay_window, record_property):
    """The instance's own HTTPS fetches are answered from the recording, none unanswered.

    Both halves are read once `OBSERVE_AFTER_BROWSER_START_SECONDS` have passed since the
    browser start.
    """
    record_property("requirement", "TST010")

    deadline = replay_window + OBSERVE_AFTER_BROWSER_START_SECONDS
    time.sleep(max(0, deadline - time.monotonic()))

    served = proxy.served()
    unserved = [url for (_method, url), count in served.items() if count == 0]
    assert not unserved, f"never served from the recording: {unserved}"

    killed = proxy.killed()
    assert not killed, f"killed, not served from the recording: {killed}"
