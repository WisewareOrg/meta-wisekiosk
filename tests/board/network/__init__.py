"""The board's network, as tests cut it off and load it."""

import contextlib
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
        cannot land inside kiosk-netcheck's window. The check is invalid if a remote shell opens halfway
        through the outage.

        Args:
            seconds: how long the network stays cut off.

        Returns:
            The host `time.monotonic()` at which the network returns, by the board's timer; taken from
            before the timer was set, so never later than the return.
        """
        self.outage.wait_boot_complete()
        cut_at = time.monotonic() + Outage.CUT_DELAY_SECONDS
        self.outage.schedule(seconds)
        time.sleep(max(0.0, cut_at + seconds / 2 - time.monotonic()))
        with invalid_if("the network did not go away: a remote shell opened while it was cut off"):
            assert not self._board.opens_a_shell()
        time.sleep(max(0.0, cut_at + seconds - time.monotonic()))
        return cut_at + seconds

    @contextlib.contextmanager
    def load(self, seconds: float) -> Iterator[None]:
        """Push random bytes at the board for `seconds`, from this host over an ssh of its own.

        The push starts on entry and ends by itself; the exit waits for it. The check is invalid if the
        board did not take every byte, or took them below 1 MB/s.

        Args:
            seconds: how long to push.

        Yields:
            None: the push runs while the body runs.
        """
        ssh = self._board.fresh_ssh_argv("ConnectTimeout=10", "ServerAliveInterval=15", "ServerAliveCountMax=4")
        push = subprocess.Popen([*ssh, "wc -c"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self._board.cleanup.callback(push.wait)
        self._board.cleanup.callback(push.kill)
        hung = threading.Timer(seconds + _HANG_GRACE_SECONDS, push.kill)
        self._board.cleanup.callback(hung.cancel)
        hung.start()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pushed = pool.submit(self._push, push, seconds)
            yield
            sent, counted, elapsed = pushed.result()
        rate = sent / elapsed / 1e6
        with invalid_if(f"the load was not applied: sent {sent} B at {rate:.2f} MB/s, the board counted {counted!r}"):
            assert push.returncode == 0 and counted == str(sent) and rate >= _LOAD_FLOOR_MB_S

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
