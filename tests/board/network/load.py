"""Bytes pushed at the board over their own ssh, from a host thread."""

import os
import subprocess
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from board import Board

_BLOCK_BYTES = 1024 * 1024
# how long past the load the push may run before it is killed as hung
_HANG_GRACE_SECONDS = 60


class NetworkLoad:
    """Random blocks written to the board's `wc -c` over an ssh of their own, from a host thread.

    Attributes:
        returncode: the ssh's return code, None until it ended.
        seconds: how long the push ran, None until it ended.
        sent: the bytes written.
        received: the byte count the board's `wc -c` returned, empty if the ssh died.
    """

    returncode: int | None
    seconds: float | None
    sent: int
    received: str

    def __init__(self, proc: subprocess.Popen, watchdog: threading.Timer, load_s: float) -> None:
        """Start pushing the blocks to `proc` for `load_s` seconds.

        Args:
            proc: the ssh whose stdin takes the blocks and whose stdout returns the board's byte count.
            watchdog: the running timer that kills `proc` if the push hangs.
            load_s: how long to push, in seconds.
        """
        self._proc = proc
        self._watchdog = watchdog
        self._load_s = load_s
        self.returncode = None
        self.seconds = None
        self.sent = 0
        self.received = ""
        self._pusher = threading.Thread(target=self._push)
        self._pusher.start()

    def is_running(self) -> bool:
        """Whether the push is still running.

        Returns:
            True until the push has ended.
        """
        return self._pusher.is_alive()

    def wait(self) -> None:
        """Wait for the push to end, then stop the hang watchdog."""
        self._pusher.join()
        self._watchdog.cancel()

    def _push(self) -> None:
        """Write random blocks to the ssh for the load's seconds, close it, and keep how it ended."""
        started = time.monotonic()
        end = started + self._load_s
        try:
            while time.monotonic() < end:
                self._proc.stdin.write(os.urandom(_BLOCK_BYTES))
                self.sent += _BLOCK_BYTES
            self._proc.stdin.close()
            self.received = self._proc.stdout.read().decode(errors="replace").strip()
        except OSError:  # the ssh died or was killed
            self.received = ""
        self.returncode = self._proc.wait()
        self.seconds = time.monotonic() - started


class Load:
    """Bytes pushed at the board."""

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board

    def push(self, load_s: float) -> NetworkLoad:
        """Start pushing random bytes at the board for `load_s` seconds, over an ssh of their own.

        When the test ends, the hang watchdog is stopped, then the ssh is killed and waited for.

        Args:
            load_s: how long to push, in seconds.

        Returns:
            The running push.
        """
        proc = subprocess.Popen(
            [
                *self._board.fresh_ssh_argv("ConnectTimeout=10", "ServerAliveInterval=15", "ServerAliveCountMax=4"),
                "wc -c",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        self._board.cleanup.callback(proc.wait)
        self._board.cleanup.callback(proc.kill)
        watchdog = threading.Timer(load_s + _HANG_GRACE_SECONDS, proc.kill)
        self._board.cleanup.callback(watchdog.cancel)
        watchdog.start()
        return NetworkLoad(proc, watchdog, load_s)
