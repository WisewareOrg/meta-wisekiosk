"""The config the WiseKiosk app runs with."""

import os
from typing import TYPE_CHECKING

from board.part import Part

if TYPE_CHECKING:
    from record import Record


# the live config's sha256 before a fault and after it, and the image default's; each None if missing
type LiveAndDefaultHashes = tuple[str | None, str | None, str | None]


class Config(Part):
    """The config the WiseKiosk app on the board runs with, and the image default it is reseeded from.

    Attributes:
        LIVE_PATH: the live config on the board.
    """

    LIVE_PATH = "/data/config/config.json"
    _DEFAULT_PATH = "/usr/share/wisekiosk/config.example.json"

    def live_sha256(self) -> str | None:
        """Read the sha256 of the live config.

        Returns:
            The hash, or None if the file is missing or unreadable.
        """
        return self._sha256(self.LIVE_PATH)

    def default_sha256(self) -> str | None:
        """Read the sha256 of the image default the board reseeds the live config from.

        Returns:
            The hash, or None if the file is missing or unreadable.
        """
        return self._sha256(self._DEFAULT_PATH)

    def assert_held(self, before: str | None, after: str | None, default: str | None, record: "Record") -> None:
        """Assert the live config held across a fault, and that a loss would have been seen.

        Records the three hashes, then `validity`: invalid when the board held no config to keep, or held
        the image default (or the default was unreadable) and kept it, so a loss and a reseed would look
        alike.

        Args:
            before: the sha256 of the live config before the fault, None if it was missing.
            after: the sha256 of the live config after the fault, None if it was missing.
            default: the sha256 of the image default the board reseeds the live config from, None if it
                was missing.
            record: the test's record.
        """
        record(config_before_sha256=before, config_after_sha256=after, config_default_sha256=default)
        if before is None:
            validity = "invalid: the board held no config.json to keep"
        elif after != before:
            validity = "valid"
        elif default is None or before == default:
            validity = "invalid: the board's config is the image default, or the default is unreadable"
        else:
            validity = "valid"
        record(validity=validity)
        assert before is not None, "INVALID CHECK, not an appliance failure: the board held no config.json to keep"
        assert after == before, (
            f"config held {'missing' if after is None else after}, expected the {before} it held before"
        )
        assert default is not None, "INVALID CHECK, not an appliance failure: the image default could not be read"
        assert before != default, (
            "INVALID CHECK, not an appliance failure: the board's config is the image default, "
            "so losing it would go unseen"
        )

    def use(self, path: str | os.PathLike[str]) -> None:
        """Swap the app onto `path`'s config, and leave the instance running against it, until the test ends.

        Each step's undo is registered once that step has succeeded, so they run in reverse even if a
        later step fails, except the backend restart's: it is registered before the page wait, so it
        still runs if that wait fails.

        Args:
            path: the config file on the host.
        """
        self._board.run("systemctl stop kiosk.service", check=True)
        self._board.cleanup.callback(self._board.run, "systemctl start kiosk.service", check=True)
        self._board.bind_over(path, self.LIVE_PATH)
        self._board.run("systemctl restart wisekiosk.service", check=True)
        self._board.cleanup.callback(self._restart_backend_and_wait)
        self._board.seconds_until(self._board.app.is_served)
        self._board.run("systemctl start kiosk.service", check=True)
        self._board.cleanup.callback(self._board.run, "systemctl stop kiosk.service", check=True)

    def _sha256(self, path: str) -> str | None:
        """Read the sha256 of the file `path` on the board.

        Args:
            path: the file on the board.

        Returns:
            The hash, or None if `sha256sum` returns nonzero (the file is missing or unreadable).
        """
        result = self._board.run(f"sha256sum {path}")
        if result.returncode != 0:
            return None
        return result.stdout[0].split()[0]

    def _restart_backend_and_wait(self) -> None:
        """Restart the backend and wait for the page."""
        self._board.run("systemctl restart wisekiosk.service", check=True)
        self._board.seconds_until(self._board.app.is_served)
