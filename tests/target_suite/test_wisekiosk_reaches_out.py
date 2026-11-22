"""Target suite: the instance's own HTTPS fetches, proved against a replayed recording."""

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from replay import CARDS4_LIVE

if TYPE_CHECKING:
    from wisebench.proxy import Proxy

OBSERVE_AFTER_BROWSER_START_SECONDS = 60


@pytest.mark.parametrize("proxy", [str(CARDS4_LIVE / "flows.har")], indirect=True)
def test_instance_reaches_out(
    proxy: "Proxy", replay_window: float, record_property: Callable[[str, object], None]
) -> None:
    """The instance's own HTTPS fetches are answered from the recording, none unanswered.

    Both halves are read once `OBSERVE_AFTER_BROWSER_START_SECONDS` have passed since the
    browser start.

    Args:
        proxy: the replaying proxy, asked which URLs it served and which it killed.
        replay_window: the browser start, as a `time.monotonic()` instant.
        record_property: records the requirement.

    Raises:
        AssertionError: a URL was never served from the recording, or a request was killed.
    """
    record_property("requirement", "TST010")

    deadline = replay_window + OBSERVE_AFTER_BROWSER_START_SECONDS
    time.sleep(max(0, deadline - time.monotonic()))

    served = proxy.served()
    unserved = [url for (_method, url), count in served.items() if count == 0]
    assert not unserved, f"never served from the recording: {unserved}"

    killed = proxy.killed()
    assert not killed, f"killed, not served from the recording: {killed}"
