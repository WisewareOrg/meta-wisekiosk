"""The board's clock, and the network time sync that corrects it."""

import json
import subprocess
import time
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from board import Board

_CLOCK_FILE = "/data/systemd-timesync/clock"
# at teardown, a clock further off the host's than this is set to the host's time
_PUT_RIGHT_ABOVE_SECONDS = 5


class ClockReading(NamedTuple):
    """One read of the board's clock.

    Attributes:
        uptime_s: the board's uptime when it was read.
        offset_s: the board's clock minus the host's.
    """

    uptime_s: float
    offset_s: float


class Clock:
    """The board's clock and systemd-timesyncd, which corrects it from the network.

    Whatever this changes is put right when the test ends, through the board's cleanup.

    Attributes:
        last_reading: the last read that succeeded, so a test that gives up still sees what the clock
            last said.
    """

    last_reading: ClockReading | None

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board this clock belongs to.
        """
        self._board = board
        self.last_reading = None

    def read(self) -> ClockReading | None:
        """Read the uptime and the clock's offset from the host's in one command.

        Returns:
            The reading, kept as `last_reading`; None if the read failed.
        """
        try:
            result = self._board.run("date +%s", with_uptime=True)
        except subprocess.TimeoutExpired:
            return None
        if result.returncode != 0:
            return None
        self.last_reading = ClockReading(result.uptime_s, int(result.stdout[0].strip()) - time.time())
        return self.last_reading

    def set(self, epoch: int) -> None:
        """Set the clock to `epoch` and persist it as the clock timesyncd restores at boot.

        Args:
            epoch: seconds since the epoch.
        """
        self._board.run(f"date -s @{epoch}", check=True)
        self._board.run(f"touch {_CLOCK_FILE}", check=True)

    def stop_sync(self) -> None:
        """Stop timesyncd; when the test ends, put the clock right and then start timesyncd again."""
        self._board.run("systemctl stop systemd-timesyncd", check=True)
        self._board.cleanup.callback(self._board.run, "systemctl start systemd-timesyncd", check=True)
        self._board.cleanup.callback(self._put_right)

    def first_sync_offset_s(self) -> float | None:
        """How far the host's clock is ahead of timesyncd's first log entry this boot.

        timesyncd restores the recorded clock at its own startup, before it logs anything, so its
        earliest entry this boot carries the restored clock. Filters on the syslog identifier rather
        than the unit, which would also match systemd's own earlier entries.

        Returns:
            Host `time.time()` minus that entry's realtime in seconds, or None if timesyncd logged
            nothing this boot.
        """
        journal = self._board.run("journalctl -q -b SYSLOG_IDENTIFIER=systemd-timesyncd -o json --no-pager", check=True)
        entries = [line for line in journal.stdout + journal.stderr if line.startswith("{")]
        if not entries:
            return None
        return time.time() - int(json.loads(entries[0])["__REALTIME_TIMESTAMP"]) / 1e6

    def sync_journal(self) -> str:
        """Read timesyncd's journal for this boot.

        Returns:
            The journal's lines, joined.
        """
        journal = self._board.run("journalctl -b -u systemd-timesyncd --no-pager", check=True)
        return "\n".join(journal.stdout + journal.stderr)

    def _put_right(self) -> None:
        """Set the clock to the host's if it is more than `_PUT_RIGHT_ABOVE_SECONDS` off."""
        reading = self.read()
        assert reading is not None, "the board's clock could not be read at teardown"
        if abs(reading.offset_s) > _PUT_RIGHT_ABOVE_SECONDS:
            self.set(int(time.time()))
