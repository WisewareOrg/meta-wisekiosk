"""The config the WiseKiosk app runs with."""

import os
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from record import Record

    from board import Board


class ConfigHashes(NamedTuple):
    """The live config's hashes on either side of a fault, and the image default's.

    Attributes:
        before: the sha256 of the live config before the fault, None if it was missing.
        after: the sha256 of the live config after the fault, None if it was missing.
        default: the sha256 of the image default the board reseeds the live config from, None if it
            was missing.
    """

    before: str | None
    after: str | None
    default: str | None

    def assert_held(self, record: "Record") -> None:
        """Assert the config held across the fault, and that a loss would have been seen.

        Records `validity` first: invalid when the board held no config to keep, or held the image
        default (or the default was unreadable) and kept it, so a loss and a reseed would look alike.

        Args:
            record: the test's record.
        """
        if self.before is None:
            validity = "invalid: the board held no config.json to keep"
        elif self.after != self.before:
            validity = "valid"
        elif self.default is None or self.before == self.default:
            validity = "invalid: the board's config is the image default, or the default is unreadable"
        else:
            validity = "valid"
        record(validity=validity)
        assert self.before is not None, "INVALID CHECK, not an appliance failure: the board held no config.json to keep"
        assert self.after == self.before, (
            f"config held {'missing' if self.after is None else self.after}, expected the {self.before} it held before"
        )
        assert self.default is not None, "INVALID CHECK, not an appliance failure: the image default could not be read"
        assert self.before != self.default, (
            "INVALID CHECK, not an appliance failure: the board's config is the image default, "
            "so losing it would go unseen"
        )


class Config:
    """The config the WiseKiosk app on the board runs with, and the image default it is reseeded from."""

    _LIVE_PATH = "/data/config/config.json"
    _DEFAULT_PATH = "/usr/share/wisekiosk/config.example.json"

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board

    def live_sha256(self) -> str | None:
        """Read the sha256 of the live config.

        Returns:
            The hash, or None if the file is missing or unreadable.
        """
        return self._board.file_sha256(self._LIVE_PATH)

    def default_sha256(self) -> str | None:
        """Read the sha256 of the image default the board reseeds the live config from.

        Returns:
            The hash, or None if the file is missing or unreadable.
        """
        return self._board.file_sha256(self._DEFAULT_PATH)

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
