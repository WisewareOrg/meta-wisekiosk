"""The network outage `outage.sh` injects: schedule it on the board, read its record back."""

import contextlib
from pathlib import Path
from typing import NamedTuple

from board import Board

_SRC = Path(__file__).resolve().parent / "outage.sh"
_SCRIPT_PATH = "/tmp/test-outage.sh"
_BOOT_COMPLETE_WAIT_SECONDS = 180


class OutageRecord(NamedTuple):
    """What the outage script's record holds.

    Attributes:
        cut: the board uptime at which the script cut the network, None if it has not.
        restored: the board uptime at which the script brought the network back (its `t0`), None if it
            has not.
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


class Outage:
    """The outage record's paths and timings, and the steps that schedule and read one.

    Each step registers its undo on the cleanup the outage was built with, once it has succeeded.

    Attributes:
        ARM_DELAY_SECONDS: the delay `systemd-run` waits before the script cuts, so the arming
            command returns first.
        GIVE_UP_SECONDS: how long after the network returns the script waits for an address before
            it reboots the board.
        RECORD_PATH: the board path of the script's record.
        UNIT: the name of the `systemd-run` unit.
    """

    ARM_DELAY_SECONDS = 3
    GIVE_UP_SECONDS = 180
    RECORD_PATH = "/tmp/test-outage.record"
    UNIT = "test-outage"

    def __init__(self, board: Board, cleanup: contextlib.ExitStack) -> None:
        """Bind to the board, and to the stack that undoes `schedule`.

        Args:
            board: the board under test.
            cleanup: registers `schedule`'s undos.
        """
        self._board = board
        self._cleanup = cleanup

    def read_record(self) -> OutageRecord:
        """The record as the board holds it, read on the SSHDriver.

        Returns:
            The record; empty if the board holds none.
        """
        return OutageRecord.from_lines(self._board.run(f"cat {self.RECORD_PATH} 2>/dev/null || true", check=True)[0])

    def wait_boot_complete(self) -> None:
        """Wait for boot-complete.target, so an outage cannot land inside kiosk-netcheck's window."""
        active_s, _ = self._board.poll(
            lambda: self._board.run("systemctl is-active boot-complete.target")[2] == 0 or None,
            until=bool,
            within=_BOOT_COMPLETE_WAIT_SECONDS,
        )
        assert active_s is not None, f"boot-complete.target was not active within {_BOOT_COMPLETE_WAIT_SECONDS} s"

    def schedule(self, outage_s: float) -> None:
        """Copy the outage script to the board and start it on a timer; undo each step at teardown.

        The SSHDriver is disconnected last, while the board is still up. Teardown reconnects it,
        stops the units, un-pins the network the record names, then removes the files.

        Args:
            outage_s: how long the script holds the network off, in seconds.
        """
        board = self._board
        board.put(str(_SRC), _SCRIPT_PATH)
        self._cleanup.callback(board.run, f"rm -f {_SCRIPT_PATH} {self.RECORD_PATH}")
        self._cleanup.callback(self._unpin)
        board.run_later(
            self._cleanup,
            self.UNIT,
            self.ARM_DELAY_SECONDS,
            f"/bin/sh {_SCRIPT_PATH} {outage_s} {self.GIVE_UP_SECONDS}",
        )
        self._cleanup.callback(board.reconnect)
        board.disconnect()

    def _unpin(self) -> None:
        """Release the network the record names from the bssid the script pinned it to."""
        for line in self.read_record().lines:
            fields = line.split()
            if fields[:1] == ["id"] and len(fields) == 2:
                self._board.run(f"wpa_cli -i wlan0 set_network {fields[1]} bssid any")
                return
