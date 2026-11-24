"""Processes on the board, found by name."""

import time
from typing import TYPE_CHECKING

from board.part import Part

if TYPE_CHECKING:
    from board import Board


class Process(Part):
    """Every process on the board with one name, or with that name under one parent."""

    def __init__(self, board: "Board", name: str, parent: str | None = None) -> None:
        """Bind to the board and say which processes these are.

        Args:
            board: the board under test.
            name: the processes' name; under a parent, a prefix of it.
            parent: the name of the process they run under, or None for any.
        """
        super().__init__(board)
        self._pids = f'$(pgrep -P "$(pidof {parent})" {name})' if parent else f"$(pidof {name})"

    def is_running(self) -> bool:
        """Whether any of the processes is running.

        Returns:
            True if one was found.
        """
        return self._board.run(f'[ -n "{self._pids}" ]').returncode == 0

    def kill(self) -> float:
        """Kill the processes outright, with SIGKILL.

        Returns:
            The host `time.monotonic()` just before the kill.
        """
        sent = time.monotonic()
        self._board.run(f"kill -KILL {self._pids}", check=True)
        return sent

    def stop(self) -> float:
        """Stop the processes with SIGSTOP; the same processes are continued when the test ends.

        Returns:
            The host `time.monotonic()` just before the stop.
        """
        pids = self._board.run(f"echo {self._pids}", check=True).text
        assert pids, "no such process to stop"
        self._board.cleanup.callback(self._board.run, f"kill -CONT {pids}")
        sent = time.monotonic()
        self._board.run(f"kill -STOP {pids}", check=True)
        return sent
