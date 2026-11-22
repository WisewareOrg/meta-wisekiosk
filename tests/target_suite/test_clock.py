"""Target suite: a clock set wrong by days and persisted across a restart is corrected."""

import json
import time
from collections.abc import Callable, Iterator

import pytest
from board import Board
from tenacity import Retrying, retry_if_exception_type, retry_if_result, stop_after_delay, wait_fixed

# the bound is TST015's
BOUND_SECONDS = 100
AGREE_SECONDS = 5
POLL_INTERVAL_SECONDS = 2
SKEW_SECONDS = 3 * 24 * 3600
SKEW_TOLERANCE_SECONDS = 24 * 3600
CLOCK_FILE = "/data/systemd-timesync/clock"


def _clock(board: Board) -> tuple[float, float] | None:
    """The board's uptime and its clock minus the host's, from one command.

    Args:
        board: the board under test.

    Returns:
        The board's uptime in seconds and board `date +%s` minus host `time.time()`, or None if the
        read returned nonzero.

    Raises:
        ExecutionError: the session failed, as `Board.timed` raises.
        subprocess.TimeoutExpired: the read ran past its timeout.
    """
    uptime, stdout, _stderr, returncode = board.timed("date +%s")
    if returncode != 0:
        return None
    return uptime, int(stdout[0].strip()) - time.time()


def _set_board_clock(board: Board, epoch: int) -> None:
    """Set the board's clock to `epoch` and record it as the persisted clock.

    Args:
        board: the board under test.
        epoch: seconds since the epoch.

    Raises:
        AssertionError: setting the clock or touching the clock file fails.
    """
    board.run(f"date -s @{epoch}", check=True)
    board.run(f"touch {CLOCK_FILE}", check=True)


@pytest.fixture
def restore_clock(board: Board) -> Iterator[None]:
    """Leave the board's clock agreeing with the host's and timesyncd running, at teardown.

    Args:
        board: the board whose clock the test sets wrong.

    Yields:
        Nothing; the restoring runs after the test.

    Raises:
        AssertionError: the board's clock cannot be read or set, or timesyncd does not start.
    """
    yield
    try:
        reading = _clock(board)
        assert reading is not None, "the board's clock could not be read at teardown"
        _uptime, offset = reading
        if abs(offset) > AGREE_SECONDS:
            _set_board_clock(board, int(time.time()))
    finally:
        board.run("systemctl start systemd-timesyncd", check=True)


def test_clock_set_wrong(
    restore_clock: Iterator[None], board: Board, record_property: Callable[[str, object], None]
) -> None:
    """The board's clock agrees with the host's within `BOUND_SECONDS` of its starting up again.

    Stops timesyncd, sets the clock three days back and records it as the persisted clock,
    then restarts the board and polls until the clock agrees. The time is the board's uptime
    at the first agreeing read. A clock that never agrees fails, since it was still wrong
    after the restart. A clock that agrees counts only if this boot's first timesyncd journal
    entry carries the clock the stimulus set, to within a day; otherwise the check is invalid.

    Args:
        restore_clock: puts the clock right and starts timesyncd after the test.
        board: the board under test.
        record_property: records the requirement and the uptime at which the clock agreed.

    Raises:
        AssertionError: the clock never agreed, the check is invalid, or it agreed after the bound.
    """
    record_property("requirement", "TST015")
    board.run("systemctl stop systemd-timesyncd", check=True)
    _set_board_clock(board, int(time.time()) - SKEW_SECONDS)

    board.restart()
    returned = time.monotonic()

    reading = Retrying(
        stop=stop_after_delay(BOUND_SECONDS - (time.monotonic() - returned)),
        wait=wait_fixed(POLL_INTERVAL_SECONDS),
        retry=retry_if_exception_type(Board.ERRORS)
        | retry_if_result(lambda read: read is None or not (abs(read[1]) <= AGREE_SECONDS or read[0] > BOUND_SECONDS)),
        retry_error_callback=Board.last_read,
    )(lambda: _clock(board))

    # timesyncd restores the recorded clock at its own startup, before it logs anything, so its
    # earliest entry this boot carries the restored clock; the syslog identifier is filtered on
    # because the unit would also match systemd's own earlier entries
    journal_cmd = "journalctl -q -b SYSLOG_IDENTIFIER=systemd-timesyncd -o json --no-pager"
    stdout, stderr, _returncode = board.run(journal_cmd, check=True)
    entries = [line for line in stdout + stderr if line.startswith("{")]
    behind = time.time() - int(json.loads(entries[0])["__REALTIME_TIMESTAMP"]) / 1e6 if entries else None
    stdout, stderr, _returncode = board.run("journalctl -b -u systemd-timesyncd --no-pager", check=True)
    print("\n".join(stdout + stderr))

    assert reading is not None, "the board's clock could not be read after the restart"
    uptime, offset = reading
    print(f"clock_corrected_seconds={uptime:.1f} final_offset_seconds={offset:.1f}")
    record_property("clock_corrected_seconds", uptime)
    assert abs(offset) <= AGREE_SECONDS, (
        f"clock still {offset:.0f}s off the network's time at uptime {uptime:.0f}s, bound {BOUND_SECONDS}s"
    )

    assert behind is not None, "INVALID CHECK, not an appliance failure: timesyncd logged nothing this boot"
    assert abs(behind - SKEW_SECONDS) < SKEW_TOLERANCE_SECONDS, (
        f"INVALID CHECK, not an appliance failure: timesyncd's first entry was {behind:.0f}s "
        f"behind the host, not the {SKEW_SECONDS}s the stimulus set"
    )
    assert uptime <= BOUND_SECONDS, f"clock agreed only at uptime {uptime:.0f}s, bound {BOUND_SECONDS}s"
