"""A systemd unit on the board."""

import time
from typing import TYPE_CHECKING

from board.part import Part

if TYPE_CHECKING:
    from board import Board

# covers a daemon-reload plus a unit start
_RELOAD_TIMEOUT_SECONDS = 60


class Unit(Part):
    """A systemd unit on the board.

    Attributes:
        name: the unit's name.
    """

    name: str

    def __init__(self, board: "Board", name: str) -> None:
        """Bind to the board and name the unit.

        Args:
            board: the board under test.
            name: the unit's name.
        """
        super().__init__(board)
        self.name = name

    def kill(self) -> float:
        """Kill every process of the unit outright, with SIGKILL.

        Returns:
            The host `time.monotonic()` just before the kill.
        """
        sent = time.monotonic()
        self._board.run(f"systemctl kill --signal=KILL {self.name}", check=True)
        return sent

    def restart(self) -> None:
        """Restart the unit."""
        self._board.run(f"systemctl restart {self.name}", check=True)

    def drop_in(self, text: str) -> None:
        """Add `text` to the unit as a runtime drop-in, until the test ends, then start the unit.

        Args:
            text: the drop-in's contents.
        """
        path = f"/run/systemd/system/{self.name}.d/test.conf"
        self._board.cleanup.callback(
            self._board.run,
            f"rm -f {path}; systemctl daemon-reload; systemctl start {self.name}",
            check=True,
            timeout=_RELOAD_TIMEOUT_SECONDS,
        )
        self._board.run(
            f"mkdir -p {path.rsplit('/', 1)[0]} && printf '{text}' > {path} && systemctl daemon-reload",
            check=True,
            timeout=_RELOAD_TIMEOUT_SECONDS,
        )
