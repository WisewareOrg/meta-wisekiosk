"""The network outage `outage.sh` injects: scheduled on the board, its record read back."""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from board import Board

_SRC = Path(__file__).resolve().parents[2] / "target_suite" / "outage.sh"
_SCRIPT_PATH = "/tmp/test-outage.sh"
_BOOT_COMPLETE_WAIT_SECONDS = 180
_FRESH_SHELL_TIMEOUT_SECONDS = 10
_JOURNAL_TIMEOUT_SECONDS = 60


class OutageRecord(NamedTuple):
    """What the outage script's record holds.

    Attributes:
        cut: the board uptime at which the script cut the network, None if it has not.
        restored: the board uptime at which the script brought the network back (its `t0`), None if
            it has not.
        lines: the record's lines.
    """

    cut: float | None
    restored: float | None
    lines: list[str]

    @classmethod
    def from_lines(cls, lines: list[str]) -> "OutageRecord":
        """Parse the record's lines.

        Args:
            lines: the record's lines, as the board holds them.

        Returns:
            The record; a field with no line is None.
        """
        return cls(cls._number_after(lines, "cut"), cls._number_after(lines, "t0"), lines)

    @staticmethod
    def _number_after(lines: list[str], name: str) -> float | None:
        """The number after the first `name` line of the record.

        Args:
            lines: the record's lines.
            name: the line's first word.

        Returns:
            The number, or None if there is no such line.
        """
        for line in lines:
            fields = line.split()
            if fields[:1] == [name]:
                return float(fields[1])
        return None


class FreshShellRead(NamedTuple):
    """One attempt to open a new ssh shell on the board and read the outage record over it.

    Attributes:
        uptime_s: the board's uptime the shell read, None if no shell opened.
        record: the outage record the shell read, None if no shell opened.
        ended: how the attempt ended: `opened`, or why no shell opened.
    """

    uptime_s: float | None
    record: OutageRecord | None
    ended: str


class Outage:
    """A network outage `outage.sh` holds on the board, and the record it keeps of it.

    Attributes:
        CUT_DELAY_SECONDS: the delay `systemd-run` waits before the script cuts, so the scheduling
            command returns first.
        GIVE_UP_SECONDS: how long after the network returns the script waits for an address before it
            reboots the board.
        RECORD_PATH: the board path of the script's record.
        UNIT: the name of the `systemd-run` unit.
    """

    CUT_DELAY_SECONDS = 3
    GIVE_UP_SECONDS = 180
    RECORD_PATH = "/tmp/test-outage.record"
    UNIT = "test-outage"

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board

    def wait_boot_complete(self) -> None:
        """Wait for boot-complete.target, so an outage cannot land inside kiosk-netcheck's window."""
        active_s, _ = self._board.poll(
            lambda: self._board.run("systemctl is-active boot-complete.target").returncode == 0 or None,
            until=bool,
            within=_BOOT_COMPLETE_WAIT_SECONDS,
        )
        assert active_s is not None, f"boot-complete.target was not active within {_BOOT_COMPLETE_WAIT_SECONDS} s"

    def schedule(self, outage_s: float) -> None:
        """Copy the outage script to the board and start it on a timer, until the test ends.

        The SSHDriver is disconnected last, while the board is still up. When the test ends, the
        SSHDriver reconnects, the units stop, the network the record names is un-pinned, and the
        files are removed.

        Args:
            outage_s: how long the script holds the network off, in seconds.
        """
        self._board.put(str(_SRC), _SCRIPT_PATH)
        self._board.cleanup.callback(self._board.run, f"rm -f {_SCRIPT_PATH} {self.RECORD_PATH}")
        self._board.cleanup.callback(self._unpin)
        self._board.run_later(
            self.UNIT, self.CUT_DELAY_SECONDS, f"/bin/sh {_SCRIPT_PATH} {outage_s} {self.GIVE_UP_SECONDS}"
        )
        self._board.cleanup.callback(self._board.reconnect)
        self._board.disconnect()

    def read_record(self) -> OutageRecord:
        """Read the record as the board holds it, over the SSHDriver.

        Returns:
            The record; empty if the board holds none.
        """
        return OutageRecord.from_lines(
            self._board.run(f"cat {self.RECORD_PATH} 2>/dev/null || true", check=True).stdout
        )

    def read_record_over_fresh_ssh(self) -> FreshShellRead:
        """Open a new ssh shell on the board, apart from the SSHDriver, and read the record over it.

        Returns:
            The board's uptime and the record the shell read, or how the attempt failed.
        """
        try:
            done = subprocess.run(
                [
                    *self._board.fresh_ssh_argv("ConnectTimeout=5"),
                    f"cat /proc/uptime; cat {self.RECORD_PATH} 2>/dev/null; true",
                ],
                capture_output=True,
                text=True,
                timeout=_FRESH_SHELL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return FreshShellRead(None, None, f"timed out after {_FRESH_SHELL_TIMEOUT_SECONDS} s")
        if done.returncode != 0:
            return FreshShellRead(None, None, f"rc {done.returncode}, stderr {done.stderr.strip()[-200:]!r}")
        lines = done.stdout.splitlines()
        return FreshShellRead(float(lines[0].split()[0]), OutageRecord.from_lines(lines[1:]), "opened")

    def journal(self, boot_id: str) -> list[str]:
        """Reconnect the SSHDriver and read the outage unit's journal for its last run in the boot `boot_id`.

        Args:
            boot_id: the boot, as `Board.BOOT_ID_CMD` prints it.

        Returns:
            The journal lines of the unit's last run, or a line naming the `journalctl` return code
            and its stderr when the read failed.
        """
        self._board.reconnect()
        journal = self._board.run(
            f"journalctl -b {boot_id.replace('-', '')} -u {self.UNIT} -o cat --no-pager",
            timeout=_JOURNAL_TIMEOUT_SECONDS,
        )
        if journal.returncode != 0:
            return [f"journalctl rc {journal.returncode}", *journal.stderr]
        last_run = max((n for n, line in enumerate(journal.stdout) if line.startswith("id ")), default=0)
        return journal.stdout[last_run:]

    def _unpin(self) -> None:
        """Release the network the record names from the bssid the script pinned it to."""
        for line in self.read_record().lines:
            fields = line.split()
            if fields[:1] == ["id"] and len(fields) == 2:
                self._board.run(f"wpa_cli -i wlan0 set_network {fields[1]} bssid any")
                return
