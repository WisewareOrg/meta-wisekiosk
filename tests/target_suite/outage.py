"""The network outage `outage.sh` injects: arm it on the board, read its record back."""

import time
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "outage.sh"
_SCRIPT_PATH = "/tmp/test-outage.sh"
_BOOT_COMPLETE_WAIT_SECONDS = 180


class Outage:
    """The outage record's paths and timings, and the steps that arm and read one.

    Attributes:
        ARM_DELAY_SECONDS (int): the delay `systemd-run` waits before the script cuts, so the
            arming command returns first.
        GIVE_UP_SECONDS (int): how long after the network returns the script waits for an
            address before it reboots the board; the callers' `give_up_s`.
        RECORD_PATH (str): the board path of the script's record.
        UNIT (str): the name of the `systemd-run` unit.
    """

    ARM_DELAY_SECONDS = 3
    GIVE_UP_SECONDS = 180
    RECORD_PATH = "/tmp/test-outage.record"
    UNIT = "test-outage"

    def __init__(self, board):
        self._board = board

    def record_lines(self):
        """The record's lines as the board holds them (empty if absent), on the SSHDriver."""
        return self._board.run(f"cat {self.RECORD_PATH} 2>/dev/null || true", check=True)[0]

    def wait_boot_complete(self):
        """Wait for boot-complete.target, so an outage cannot land inside kiosk-netcheck's window."""
        deadline = time.monotonic() + _BOOT_COMPLETE_WAIT_SECONDS
        while self._board.run("systemctl is-active boot-complete.target")[2] != 0:
            assert time.monotonic() < deadline, (
                f"boot-complete.target was not active within {_BOOT_COMPLETE_WAIT_SECONDS} s"
            )
            time.sleep(1)

    def arm(self, request, outage_s, give_up_s):
        """Copy the outage script to the board and start it on a timer; undo each step at teardown.

        The SSHDriver is disconnected last, while the board is still up. Teardown reconnects it,
        stops the units, un-pins the network the record names, then removes the files.
        """
        board = self._board
        board.put(str(_SRC), _SCRIPT_PATH)
        request.addfinalizer(lambda: board.run(f"rm -f {_SCRIPT_PATH} {self.RECORD_PATH}"))

        def unpin():
            for line in self.record_lines():
                fields = line.split()
                if fields[:1] == ["id"] and len(fields) == 2:
                    board.run(f"wpa_cli -i wlan0 set_network {fields[1]} bssid any")
                    return

        request.addfinalizer(unpin)

        board.run(
            f"systemd-run --unit={self.UNIT} --on-active={self.ARM_DELAY_SECONDS} "
            f"--timer-property=AccuracySec=100ms /bin/sh {_SCRIPT_PATH} {outage_s} {give_up_s}",
            check=True,
        )
        units = f"{self.UNIT}.timer {self.UNIT}.service"
        request.addfinalizer(
            lambda: board.run(f"systemctl stop {units}; systemctl reset-failed {units}")
        )

        request.addfinalizer(board.reconnect)
        board.disconnect()

    @staticmethod
    def field(lines, name):
        """The number after the first `name` line of the record, else None."""
        for line in lines:
            fields = line.split()
            if fields[:1] == [name]:
                return float(fields[1])
        return None
