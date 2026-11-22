"""The config the WiseKiosk app runs with."""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from board import Board


class Config:
    """The config the WiseKiosk app on the board runs with."""

    _LIVE_PATH = "/data/config/config.json"

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board

    def use(self, path: str | os.PathLike[str]) -> None:
        """Swap the app onto `path`'s config, and leave the instance running against it, until the test ends.

        Stops the browser, bind-mounts a copy of `path` over the live config, restarts the backend and
        waits for the page, then starts the browser. Each step's undo is registered once that step
        has succeeded, so they run in reverse even if a later step fails, except the backend
        restart's: it is registered right after the restart and before the page wait, so it still
        runs if that wait fails.

        Args:
            path: the config file on the host.
        """
        self._board.run("systemctl stop kiosk.service", check=True)
        self._board.cleanup.callback(self._board.run, "systemctl start kiosk.service", check=True)
        self._board.bind_over(path, self._LIVE_PATH)
        self._board.run("systemctl restart wisekiosk.service", check=True)
        self._board.cleanup.callback(self._restart_backend_and_wait)
        self._board.wait_for_page()
        self._board.run("systemctl start kiosk.service", check=True)
        self._board.cleanup.callback(self._board.run, "systemctl stop kiosk.service", check=True)

    def _restart_backend_and_wait(self) -> None:
        """Restart the backend and wait for the page."""
        self._board.run("systemctl restart wisekiosk.service", check=True)
        self._board.wait_for_page()
