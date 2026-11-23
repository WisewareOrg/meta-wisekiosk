"""The board's network, as tests cut it off and load it."""

import contextlib
import dataclasses
import os
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

    def confirm_applied(self) -> None:
        """Fail the check as invalid unless the board took every byte, at 1 MB/s or more."""
        rate = self.sent / self.seconds / 1e6 if self.seconds else 0.0
        with invalid_if(
            f"the load was not applied: {self.sent} B at {rate:.2f} MB/s, the board counted {self.counted!r}"
        ):
            assert self.returncode == 0 and self.counted == str(self.sent) and rate >= _LOAD_FLOOR_MB_S


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
            f"the board did not rejoin: the outage restarted it, {Outage.GIVE_UP_SECONDS} s after the network returned"
        )
        read_at = time.monotonic()
        uptime_s, record = self.outage.uptime_and_record()
        with invalid_if(f"the record does not show the board cut off and back: {record.lines}"):
            assert record.cut is not None and record.restored is not None
            assert record.offline_at((record.cut + record.restored) / 2)
        return read_at - (uptime_s - record.restored)

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
