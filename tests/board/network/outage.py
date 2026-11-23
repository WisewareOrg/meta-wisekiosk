"""The network outage `outage.sh` injects: scheduled on the board, its record read back."""

from pathlib import Path
from typing import NamedTuple

from board.part import Part

_SRC = Path(__file__).resolve().parents[2] / "target_suite" / "outage.sh"
_SCRIPT_PATH = "/tmp/test-outage.sh"
_RECORD_PATH = "/tmp/test-outage.record"
_UNIT = "test-outage"
_BOOT_COMPLETE_WAIT_SECONDS = 180


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
            The record, from the first `cut` line and the first `t0` line; a field with no line is None.
        """
        first = {}
        for line in lines:
            fields = line.split()
            if fields[:1] in (["cut"], ["t0"]) and fields[0] not in first:
                first[fields[0]] = float(fields[1])
        return cls(first.get("cut"), first.get("t0"), lines)


class Outage(Part):
    """A network outage `outage.sh` holds on the board, and the record it keeps of it.

    Attributes:
        CUT_DELAY_SECONDS: the delay `systemd-run` waits before the script cuts, so the scheduling
            command returns first.
        GIVE_UP_SECONDS: how long after the network returns the script waits for an address before it
            reboots the board.
    """

    CUT_DELAY_SECONDS = 3
    GIVE_UP_SECONDS = 180

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
        self._board.cleanup.callback(self._board.run, f"rm -f {_SCRIPT_PATH} {_RECORD_PATH}")
        self._board.cleanup.callback(self._unpin)
        self._board.run_later(
            _UNIT, self.CUT_DELAY_SECONDS, f"/bin/sh {_SCRIPT_PATH} {outage_s} {self.GIVE_UP_SECONDS}"
        )
        self._board.cleanup.callback(self._board.reconnect)
        self._board.disconnect()

    def uptime_and_return(self) -> tuple[float, float | None]:
        """Read the board's uptime, and the uptime the record says the network returned at, in one command.

        Returns:
            The uptime, and the record's `t0`, None if it holds none.
        """
        lines = self._board.run(f"cat /proc/uptime; cat {_RECORD_PATH} 2>/dev/null || true", check=True).stdout
        return float(lines[0].split()[0]), OutageRecord.from_lines(lines[1:]).restored

    def read_record(self) -> OutageRecord:
        """Read the record as the board holds it, over the SSHDriver.

        Returns:
            The record; empty if the board holds none.
        """
        return OutageRecord.from_lines(self._board.run(f"cat {_RECORD_PATH} 2>/dev/null || true", check=True).stdout)

    def _unpin(self) -> None:
        """Release the network the record names from the bssid the script pinned it to."""
        for line in self.read_record().lines:
            fields = line.split()
            if fields[:1] == ["id"] and len(fields) == 2:
                self._board.run(f"wpa_cli -i wlan0 set_network {fields[1]} bssid any")
                return
