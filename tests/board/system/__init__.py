"""The board's operating system: its clock and the network time that corrects it, its zone, memory and log."""

import json
import time
from typing import TYPE_CHECKING

from board.part import Part, invalid_if
from board.system.journal import Journal
from board.system.kernel import Kernel
from board.system.memory import Memory
from board.system.soak import Soak
from board.system.timezone import Timezone

if TYPE_CHECKING:
    from board import Board

# the clock timesyncd restores at boot
_CLOCK_FILE = "/data/systemd-timesync/clock"
# how far back TST015 sets the clock, and how near that timesyncd's first entry must show it
_CLOCK_WRONG_BY_SECONDS = 3 * 24 * 3600
_STILL_WRONG_WITHIN_SECONDS = 24 * 3600
# the clock agrees with the network's time this close to the host's
_AGREES_WITHIN_SECONDS = 5


class System(Part):
    """The board's operating system.

    Attributes:
        timezone: the zone and the local time.
        memory: memory and the kernel's out-of-memory record.
        soak: the kiosk-soak sampler, its timer and its log.
        kernel: what the running kernel reports.
        journal: the system journal's test markers.
    """

    timezone: Timezone
    memory: Memory
    soak: Soak
    kernel: Kernel
    journal: Journal

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        super().__init__(board)
        self.timezone = Timezone(board)
        self.memory = Memory(board)
        self.soak = Soak(board)
        self.kernel = Kernel(board)
        self.journal = Journal(board)

    def restart_with_clock_wrong(self) -> float:
        """Set the clock three days back where timesyncd restores it from, and restart the board.

        timesyncd is stopped first, so it cannot put the clock right before the restart; when the test
        ends the clock is set to the host's and timesyncd started again. The check is invalid if the
        clock is not still wrong after the restart, as timesyncd's first entry of the new boot shows it.

        Returns:
            The host `time.monotonic()` at which the board started up again.
        """
        self._board.cleanup.callback(self._board.run, "systemctl start systemd-timesyncd", check=True)
        self._board.cleanup.callback(self._put_clock_right)
        self._board.run("systemctl stop systemd-timesyncd", check=True)
        self._set_clock(int(time.time()) - _CLOCK_WRONG_BY_SECONDS)
        self._board.restart()
        started_up = time.monotonic() - self._board.uptime_s()
        with invalid_if("the clock was not still wrong after the restart"):
            behind_s = self._first_sync_entry_behind_s()
            assert abs(behind_s - _CLOCK_WRONG_BY_SECONDS) < _STILL_WRONG_WITHIN_SECONDS, f"{behind_s:.0f} s behind"
        return started_up

    def clock_agrees(self) -> bool:
        """Whether the board's clock agrees with the network's time, which the host's is synchronised to.

        Returns:
            True if it is within 5 s of the host's.
        """
        return abs(self._clock_ahead_s()) <= _AGREES_WITHIN_SECONDS

    def _clock_ahead_s(self) -> float:
        """Read how far the board's clock is ahead of the host's.

        Returns:
            The seconds, negative when behind.
        """
        return int(self._board.run("date +%s", check=True).text) - time.time()

    def _set_clock(self, epoch: int) -> None:
        """Set the clock to `epoch`, and record it as the clock timesyncd restores at boot.

        Args:
            epoch: seconds since the epoch.
        """
        self._board.run(f"date -s @{epoch} && touch {_CLOCK_FILE}", check=True)

    def _put_clock_right(self) -> None:
        """Set the clock to the host's, unless it already agrees."""
        if not self.clock_agrees():
            self._set_clock(int(time.time()))

    def _first_sync_entry_behind_s(self) -> float:
        """How far timesyncd's first entry this boot is behind the host's clock.

        timesyncd restores the recorded clock at its own start, before it logs anything, so its earliest
        entry this boot carries the restored clock. The read filters on the syslog identifier, not the
        unit, which would also match systemd's own earlier entries.

        Returns:
            The seconds behind.
        """
        journal = self._board.run("journalctl -q -b SYSLOG_IDENTIFIER=systemd-timesyncd -o json --no-pager", check=True)
        entries = [line for line in journal.stdout if line.startswith("{")]
        assert entries, "timesyncd logged nothing this boot"
        return time.time() - int(json.loads(entries[0])["__REALTIME_TIMESTAMP"]) / 1e6
