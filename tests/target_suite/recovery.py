"""Whether a board that went down serves the instance again: the page served with the browser running."""

import subprocess
import time

from labgrid.driver.exception import ExecutionError

# stop polling; past every bound, so the record still carries the time it took
GIVE_UP_SECONDS = 180


def instance_up(board):
    """Read whether the browser is running and whether the page is served, as a pair."""
    try:
        _, _, browser = board.run("pgrep -x surf")
    except (ExecutionError, subprocess.TimeoutExpired):
        browser = None
    try:
        page_served = board.page_served()
    except ExecutionError:
        page_served = False
    return browser == 0, page_served


def poll_from(started, read, done):
    """Poll `read` once a second from `started` until `done(value)`; return seconds and the last value.

    Seconds is None when `GIVE_UP_SECONDS` passed first, and overstates by at most one read plus the
    1 s sleep. A read returning None is a failed read: it does not replace the last value.
    """
    last = None
    while True:
        value = read()
        if value is not None:
            last = value
            if done(value):
                return round(time.monotonic() - started, 1), last
        if time.monotonic() - started > GIVE_UP_SECONDS:
            return None, last
        time.sleep(1)


def until_up(board, started):
    """Poll from `started` until the instance is up; return seconds (None if never) and the last read."""
    return poll_from(started, lambda: instance_up(board), all)


def assert_back_within(back_s, last_read, fault, requirement, bound):
    """Assert the instance was back, and within the bound."""
    assert back_s is not None, (
        f"the board did not serve the page with the browser running within {GIVE_UP_SECONDS} s "
        f"of the {fault}; last read: browser running {last_read[0]}, page served {last_read[1]}"
    )
    assert back_s <= bound, (
        f"back after {back_s} s; {requirement}'s bound is {bound} s"
    )
