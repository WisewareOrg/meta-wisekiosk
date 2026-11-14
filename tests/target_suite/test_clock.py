"""Target suite: a clock set wrong by days and persisted across a restart is corrected."""

import json
import time

import pytest

from page import POLL_INTERVAL_SECONDS

# the bound is TST015's
BOUND_SECONDS = 100
AGREE_SECONDS = 5
SKEW_SECONDS = 3 * 24 * 3600
STILL_WRONG_SECONDS = 24 * 3600
CLOCK_FILE = "/data/systemd-timesync/clock"


def _restored_clock_offset(board):
    """How far behind the host the clock was when timesyncd first logged this boot.

    timesyncd restores the recorded clock at its own startup, before it logs anything, so
    its earliest entry this boot carries the restored clock. Filters on the syslog
    identifier rather than the unit, which would also match systemd's own earlier entries.

    Args:
        board (Board): the board under test.

    Returns:
        float | None: host `time.time()` minus that entry's realtime in seconds, or None if
            timesyncd logged nothing this boot.

    Raises:
        AssertionError: the journal cannot be read.
    """
    cmd = "journalctl -q -b SYSLOG_IDENTIFIER=systemd-timesyncd -o json --no-pager"
    stdout, stderr, _returncode = board.run(cmd, check=True)
    entries = [line for line in stdout + stderr if line.startswith("{")]
    if not entries:
        return None
    return time.time() - int(json.loads(entries[0])["__REALTIME_TIMESTAMP"]) / 1e6


def _set_board_clock(board, epoch):
    """Set the board's clock to `epoch` and record it as the persisted clock.

    Args:
        board (Board): the board under test.
        epoch (int): seconds since the epoch.

    Raises:
        AssertionError: setting the clock or touching the clock file fails.
    """
    board.run(f"date -s @{epoch}", check=True)
    board.run(f"touch {CLOCK_FILE}", check=True)


@pytest.fixture
def restore_clock(board):
    """Leave the board's clock agreeing with the host's and timesyncd running, at teardown.

    Args:
        board (Board): the board under test.
    """
    yield
    reading = board.clock()
    assert reading is not None, "the board's clock could not be read at teardown"
    if abs(reading[1]) > AGREE_SECONDS:
        _set_board_clock(board, int(time.time()))
    board.run("systemctl start systemd-timesyncd", check=True)


def test_clock_set_wrong(restore_clock, board, record_property):
    """The board's clock agrees with the host's within `BOUND_SECONDS` of its starting up again.

    Stops timesyncd, sets the clock three days back and records it as the persisted clock,
    then restarts the board and polls until the clock agrees. The time is the board's uptime
    at the first agreeing read. The check is invalid unless this boot's first timesyncd
    journal entry carries the clock the stimulus set, to within a day; that verdict comes
    before the pass conditions.
    """
    record_property("requirement", "TST015")
    board.run("systemctl stop systemd-timesyncd", check=True)
    _set_board_clock(board, int(time.time()) - SKEW_SECONDS)

    board.restart()
    returned = time.monotonic()

    reading = None
    while True:
        latest = board.clock()
        if latest is not None:
            reading = latest
            uptime, offset = reading
            if abs(offset) <= AGREE_SECONDS or uptime > BOUND_SECONDS:
                break
        elif time.monotonic() - returned > BOUND_SECONDS:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    behind = _restored_clock_offset(board)
    stdout, stderr, _returncode = board.run("journalctl -b -u systemd-timesyncd --no-pager", check=True)
    print("\n".join(stdout + stderr))
    assert behind is not None, (
        "INVALID CHECK, not an appliance failure: timesyncd logged nothing this boot"
    )
    assert abs(behind - SKEW_SECONDS) < STILL_WRONG_SECONDS, (
        f"INVALID CHECK, not an appliance failure: timesyncd's first entry was {behind:.0f}s "
        f"behind the host, not the {SKEW_SECONDS}s the stimulus set"
    )

    assert reading is not None, "the board's clock could not be read after the restart"
    uptime, offset = reading
    print(f"clock_corrected_seconds={uptime:.1f} final_offset_seconds={offset:.1f}")
    record_property("clock_corrected_seconds", uptime)
    assert abs(offset) <= AGREE_SECONDS, (
        f"clock still {offset:.0f}s off the network's time at uptime {uptime:.0f}s, "
        f"bound {BOUND_SECONDS}s"
    )
    assert uptime <= BOUND_SECONDS, f"clock agreed only at uptime {uptime:.0f}s, bound {BOUND_SECONDS}s"
