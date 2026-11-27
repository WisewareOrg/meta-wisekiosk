"""The board's operating system: its clock and the network time that corrects it, its time zone, memory and log."""

import json
import time
from typing import TYPE_CHECKING

from labgrid.driver.exception import ExecutionError

from board.part import Part, invalid_if
from board.system.memory import Memory

if TYPE_CHECKING:
    from board import Board

# the clock timesyncd restores at boot
_CLOCK_FILE = "/data/systemd-timesync/clock"
# how far back TST015 Clock set wrong sets the clock, and how near that timesyncd's first entry must show it
_CLOCK_WRONG_BY_SECONDS = 3 * 24 * 3600
_STILL_WRONG_WITHIN_SECONDS = 24 * 3600
# the clock agrees with the network's time this close to the host's
_AGREES_WITHIN_SECONDS = 5
# where a zone set lands instead of the rootfs's /etc
_ETC_OVERLAY_DIR = "/run/tst026"


class System(Part):
    """The board's operating system.

    Attributes:
        memory: memory over a long run, and the kernel's record of what it killed for it.
    """

    memory: Memory

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        super().__init__(board)
        self.memory = Memory(board)

    def restart_with_clock_wrong(self) -> float:
        """Set the clock three days back where timesyncd restores it from, and restart the board.

        timesyncd is stopped first, so it cannot put the clock right before the restart; when the test
        ends the clock is set to the host's and timesyncd started again. The check is invalid if the
        clock is not still wrong after the restart, as timesyncd's first entry of the new boot shows it.

        Returns:
            The host `time.monotonic()` at which the board started up again, taken from before the uptime
            read, so never later than the start.
        """
        self._board.cleanup.callback(self._board.run, "systemctl start systemd-timesyncd", check=True)
        self._board.cleanup.callback(self._put_clock_right)
        self._board.run("systemctl stop systemd-timesyncd", check=True)
        self._set_clock(int(time.time()) - _CLOCK_WRONG_BY_SECONDS)
        self._board.restart()
        read_at = time.monotonic()
        started_up = read_at - self._board.uptime_s()
        with invalid_if("the clock was not still wrong after the restart"):
            behind_s = self._first_sync_entry_behind_s()
            assert abs(behind_s - _CLOCK_WRONG_BY_SECONDS) < _STILL_WRONG_WITHIN_SECONDS, f"{behind_s:.0f} s behind"
        return started_up

    def clock_agrees(self) -> bool:
        """Whether the board's clock agrees with the network's time, which the host's is synchronised to.

        Returns:
            True if it is within 5 s of the host's; False if the clock could not be read.
        """
        date = self._board.run("date +%s")
        if date.returncode != 0 or not date.text.isdigit():
            return False
        return abs(int(date.text) - time.time()) <= _AGREES_WITHIN_SECONDS

    def mark_log(self, text: str) -> None:
        """Write `text` to the board's log, under the identifier `kiosk-log-marker`.

        Args:
            text: the line.
        """
        self._board.run(f"echo {text} | systemd-cat -t kiosk-log-marker", check=True)

    def log_markers(self) -> list[str]:
        """Read the lines written to the board's log under the identifier `kiosk-log-marker`, in every boot.

        Returns:
            The lines.

        Raises:
            ExecutionError: the log could not be read; a wait takes it as a read that does not hold.
        """
        journal = self._board.run("journalctl -t kiosk-log-marker -o cat --no-pager")
        if journal.returncode != 0:
            raise ExecutionError("journalctl -t kiosk-log-marker", journal.stdout, journal.stderr)
        return journal.stdout

    def utc_offset(self) -> str:
        """Read the local time's offset from UTC, as `date +%z` prints it.

        Returns:
            The offset, e.g. `+0900`.
        """
        return self._board.run("date +%z", check=True).text

    def overlay_etc(self) -> None:
        """Overlay /etc, so a time zone set lands in /run and never writes the rootfs, until the test ends.

        What a dead run left of the overlay is cleared first. timedated is stopped before the mount, so
        the next `timedatectl` starts it inside the overlay. When the test ends, /etc is unmounted, and
        asserted back as it was.
        """
        board = self._board
        board.run("while findmnt -n /etc >/dev/null; do umount -l /etc || exit 1; done", check=True)
        board.run(f"rm -rf {_ETC_OVERLAY_DIR}", check=True)
        localtime = board.run("readlink /etc/localtime", check=True).text
        board.run(f"modprobe overlay && mkdir -p {_ETC_OVERLAY_DIR}/upper {_ETC_OVERLAY_DIR}/work", check=True)
        board.cleanup.callback(board.run, f"rm -rf {_ETC_OVERLAY_DIR}", check=True)
        board.run("systemctl stop systemd-timedated", check=True)
        board.run(
            f"mount -t overlay tst026 -o lowerdir=/etc,upperdir={_ETC_OVERLAY_DIR}/upper,"
            f"workdir={_ETC_OVERLAY_DIR}/work /etc",
            check=True,
        )
        board.cleanup.callback(self._unmount_etc, localtime)

    def set_timezone(self, zone: str) -> None:
        """Set the time zone over the air, with `timedatectl`.

        Args:
            zone: the zone's name, e.g. `Asia/Tokyo`.
        """
        self._board.run(f"timedatectl set-timezone {zone}", check=True)

    def _unmount_etc(self, localtime: str) -> None:
        """Stop timedated and unmount the /etc overlay; assert it is gone and `/etc/localtime` is as it was.

        Args:
            localtime: where `/etc/localtime` pointed before the overlay.
        """
        self._board.run("systemctl stop systemd-timedated")
        self._board.run("umount -l /etc", check=True)
        assert self._board.run("findmnt -n /etc").returncode != 0, "the /etc overlay is still mounted"
        restored = self._board.run("readlink /etc/localtime", check=True).text
        assert restored == localtime, f"/etc/localtime is {restored}, expected {localtime}"

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
