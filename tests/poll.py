"""Poll a board read until a condition holds, keeping the last good read.

tenacity, the runner's retry library, retries on a raise or a result but hands back only the last
attempt's outcome; a poll here keeps the last good read across failed ones and times from an
instant taken before it began.
"""

import subprocess
import time
from collections.abc import Callable

from labgrid.binding import StateError
from labgrid.driver.exception import ExecutionError

# stop polling; past every bound, so the record still carries the time it took
GIVE_UP_SECONDS = 180
# what a read of the board raises when the board does not answer
BOARD_ERRORS = (ExecutionError, StateError, subprocess.TimeoutExpired)


def poll[T](
    read: Callable[[], T | None],
    done: Callable[[T], object],
    within: float,
    every: float = 1,
    since: float | None = None,
) -> tuple[float | None, T | None]:
    """Call `read` every `every` seconds until `done` accepts a value, or `within` seconds pass.

    A read that raises one of `BOARD_ERRORS`, or returns None, is a failed read: it does not
    replace the last value and `done` is not asked. The bound is checked after each read, so the
    last read may land one read past it.

    Args:
        read: reads the board once; None means nothing was read.
        done: whether a read value ends the poll.
        within: seconds from `since` after which the poll gives up.
        every: seconds slept between reads.
        since: the `time.monotonic()` instant the poll counts from; the start of the first read
            when None.

    Returns:
        The seconds from `since` to the first value `done` accepted, rounded to 0.1 s, and that
        value; None and the last good read (None if there was none) when `within` passed first.
    """
    since = time.monotonic() if since is None else since
    last = None
    while True:
        try:
            value = read()
        except BOARD_ERRORS:
            value = None
        if value is not None:
            last = value
            if done(value):
                return round(time.monotonic() - since, 1), value
        if time.monotonic() - since > within:
            return None, last
        time.sleep(every)
