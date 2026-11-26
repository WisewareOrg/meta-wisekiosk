"""The board's network, as tests cut it off and load it."""

import contextlib
import dataclasses
import os
import re
import subprocess
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from board.network.outage import Outage
from board.part import Part, invalid_if

if TYPE_CHECKING:
    from board import Board

_BLOCK_BYTES = 1024 * 1024
# how long past the load the push may run before it is killed as hung
_HANG_GRACE_SECONDS = 60
# the least average rate that counts as the load applied
_LOAD_FLOOR_MB_S = 1.0
# one read of the board's radio: its boot, the station's counters and wlan0's byte counts
_RADIO_READ = (
    "echo boot_id: $(cat /proc/sys/kernel/random/boot_id); iw dev wlan0 station dump; "
    "echo rx_bytes: $(cat /sys/class/net/wlan0/statistics/rx_bytes); "
    "echo tx_bytes: $(cat /sys/class/net/wlan0/statistics/tx_bytes)"
)
_RADIO_READ_TIMEOUT_SECONDS = 10
# how far the station's connected time may fall short of the host's window before it counts as a reconnect
_RECONNECT_SLACK_SECONDS = 2


@dataclasses.dataclass
class Load:
    """A push of random bytes at the board, once it has ended.

    Attributes:
        sent: the bytes written.
        counted: the byte count the board returned, empty if the ssh died.
        seconds: how long the push ran.
        returncode: the ssh's return code.
    """

    sent: int = 0
    counted: str = ""
    seconds: float = 0.0
    returncode: int | None = None

    @property
    def mb_s(self) -> float:
        """The push's average rate, in 10^6 bytes a second; 0 if it never ran."""
        return self.sent / self.seconds / 1e6 if self.seconds else 0.0

    def confirm_applied(self) -> None:
        """Fail the check as invalid unless the board took every byte, at 1 MB/s or more."""
        rate = self.sent / self.seconds / 1e6 if self.seconds else 0.0
        with invalid_if(
            f"the load was not applied: {self.sent} B at {rate:.2f} MB/s, the board counted {self.counted!r}"
        ):
            assert self.returncode == 0 and self.counted == str(self.sent) and rate >= _LOAD_FLOOR_MB_S


@dataclasses.dataclass(frozen=True)
class Radio:
    """The board's radio at one instant: the station's counters, its signal, and wlan0's byte counts.

    Attributes:
        at: the host `time.monotonic()` just before the read.
        done: the host `time.monotonic()` just after it.
        boot_id: the board's boot.
        connected_s: how long the station has been associated.
        signal_dbm: the station's signal.
        tx_retries: frames the board sent again.
        tx_failed: frames the board gave up on.
        rx_bytes: wlan0's received bytes.
        tx_bytes: wlan0's sent bytes.
    """

    at: float
    done: float
    boot_id: str
    connected_s: int
    signal_dbm: int
    tx_retries: int
    tx_failed: int
    rx_bytes: int
    tx_bytes: int

    _FIELDS = {
        "boot_id": r"^boot_id:\s*(\S+)",
        "connected_s": r"^\s*connected time:\s*(\d+)",
        "signal_dbm": r"^\s*signal:\s*(-?\d+)",
        "tx_retries": r"^\s*tx retries:\s*(\d+)",
        "tx_failed": r"^\s*tx failed:\s*(\d+)",
        "rx_bytes": r"^rx_bytes:\s*(\d+)",
        "tx_bytes": r"^tx_bytes:\s*(\d+)",
    }

    @classmethod
    def parse(cls, lines: list[str], at: float, done: float) -> "Radio":
        """Read one `_RADIO_READ`'s output; the first station's counters count.

        Args:
            lines: the read's stdout lines.
            at: the host `time.monotonic()` just before the read.
            done: the host `time.monotonic()` just after it.

        Returns:
            The radio at `at`.

        Raises:
            ValueError: a field is missing, by its name in the read.
        """
        text = "\n".join(lines)
        values: dict[str, int | str] = {}
        for name, pattern in cls._FIELDS.items():
            found = re.search(pattern, text, re.MULTILINE)
            if not found or not found.group(1):
                raise ValueError(f"no {name.replace('_', ' ')} in the read")
            values[name] = found.group(1) if name == "boot_id" else int(found.group(1))
        return cls(at=at, done=done, **values)

    @staticmethod
    def properties(before: "Radio | str", after: "Radio | str") -> dict[str, object]:
        """The record's radio properties for a window between two reads.

        A read that failed is its error text: that edge's numbers and every delta are left out. Deltas are
        left out too, with the reason as the after-read's error, when the window spans a new boot, a
        counter that went back, or a reconnect of the station: its connected time grew by less than the
        window, less `_RECONNECT_SLACK_SECONDS`. The window runs from the end of the before-read to the start
        of the after-read.

        Args:
            before: the read before the window, or why it failed.
            after: the read after the window, or why it failed.

        Returns:
            The properties, by name.
        """
        properties: dict[str, object] = {}
        for edge, radio in (("before", before), ("after", after)):
            if isinstance(radio, str):
                properties[f"radio_read_error_{edge}"] = radio
            else:
                properties[f"radio_signal_{edge}_dbm"] = radio.signal_dbm
        if isinstance(before, str) or isinstance(after, str):
            return properties
        deltas = {
            "radio_tx_retries_delta": after.tx_retries - before.tx_retries,
            "radio_tx_failed_delta": after.tx_failed - before.tx_failed,
            "wlan0_rx_bytes_delta": after.rx_bytes - before.rx_bytes,
            "wlan0_tx_bytes_delta": after.tx_bytes - before.tx_bytes,
        }
        window_s = after.at - before.done
        went_back = [name for name, delta in deltas.items() if delta < 0]
        if after.boot_id != before.boot_id:
            properties["radio_read_error_after"] = "boot changed"
        elif went_back:
            properties["radio_read_error_after"] = f"counter went back: {went_back[0]}"
        elif after.connected_s < before.connected_s + window_s - _RECONNECT_SLACK_SECONDS:
            properties["radio_read_error_after"] = (
                f"station reconnected: connected {before.connected_s} then {after.connected_s} over {window_s:.0f} s"
            )
        else:
            properties.update(deltas, radio_window_s=round(window_s, 1))
        return properties


class Network(Part):
    """The board's network.

    Attributes:
        outage: a scheduled network outage and its record.
    """

    outage: Outage

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        super().__init__(board)
        self.outage = Outage(board)

    def cut_off(self, seconds: float) -> float:
        """Cut the board off the site network at the board itself for `seconds`, then let it back on.

        A timer on the board cuts and restores the network, once boot has completed, so the outage
        cannot land inside kiosk-netcheck's window. Once the restore is due, the board is reconnected. A
        board in a new boot fails the test: the outage restarts a board that has no address
        `Outage.GIVE_UP_SECONDS` after the network returned. Otherwise the outage's record is read, and the
        check is invalid unless it shows the board without an address halfway through.

        Args:
            seconds: how long the network stays cut off.

        Returns:
            The host `time.monotonic()` at which the board let the network back on: the record's `t0`,
            the board's uptime then, mapped from an uptime read whose host instant is taken before it,
            so it is never later than the return.
        """
        self.outage.wait_boot_complete()
        boot = self._board.boot_id()
        cut_at = time.monotonic() + Outage.CUT_DELAY_SECONDS
        self.outage.schedule(seconds)
        time.sleep(max(0.0, cut_at + seconds - time.monotonic()))
        self._board.reconnect()
        assert self._board.boot_id() == boot, (
            "the board restarted during the outage "
            f"(outage.sh restarts a board with no address {Outage.GIVE_UP_SECONDS} s after the network returns)"
        )
        read_at = time.monotonic()
        uptime_s, record = self.outage.uptime_and_record()
        with invalid_if(f"the record does not show the board cut off and back: {record.lines}"):
            assert record.cut is not None and record.restored is not None
            assert record.offline_at((record.cut + record.restored) / 2)
        return read_at - (uptime_s - record.restored)

    def radio(self) -> "Radio | str":
        """Read the board's radio once; a read that fails is returned as why, never raised.

        Returns:
            The radio now, or the reason the read failed.
        """
        at = time.monotonic()
        try:
            lines = self._board.run(_RADIO_READ, check=True, timeout=_RADIO_READ_TIMEOUT_SECONDS).stdout
            return Radio.parse(lines, at, time.monotonic())
        except (AssertionError, ValueError, *self._board.ERRORS) as error:
            return str(error) or type(error).__name__

    @contextlib.contextmanager
    def load(self, seconds: float) -> Iterator["Load"]:
        """Push random bytes at the board for `seconds`, from this host over an ssh of its own.

        The push starts on entry and ends by itself; the exit waits for it, and leaves how it went on the
        `Load`, whose `confirm_applied` judges it once the test has judged the panel.

        Args:
            seconds: how long to push.

        Yields:
            Load: the push, which runs while the body runs.
        """
        ssh = self._board.fresh_ssh_argv("ConnectTimeout=10", "ServerAliveInterval=15", "ServerAliveCountMax=4")
        push = subprocess.Popen([*ssh, "wc -c"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self._board.cleanup.callback(push.wait)
        self._board.cleanup.callback(push.kill)
        hung = threading.Timer(seconds + _HANG_GRACE_SECONDS, push.kill)
        self._board.cleanup.callback(hung.cancel)
        hung.start()
        load = Load()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pushed = pool.submit(self._push, push, seconds)
            yield load
            load.sent, load.counted, load.seconds = pushed.result()
        load.returncode = push.returncode

    @staticmethod
    def _push(ssh: subprocess.Popen, seconds: float) -> tuple[int, str, float]:
        """Write random blocks to `ssh` for `seconds`, then close it and read back the board's count.

        Args:
            ssh: the ssh whose stdin takes the blocks and whose stdout returns the board's byte count.
            seconds: how long to write.

        Returns:
            The bytes written, the count the board returned (empty if the ssh died), and the seconds the
            push took.
        """
        started = time.monotonic()
        sent = 0
        try:
            while time.monotonic() < started + seconds:
                ssh.stdin.write(os.urandom(_BLOCK_BYTES))
                sent += _BLOCK_BYTES
            ssh.stdin.close()
            counted = ssh.stdout.read().decode(errors="replace").strip()
        except OSError:  # the ssh died or was killed
            counted = ""
        ssh.wait()
        return sent, counted, time.monotonic() - started
