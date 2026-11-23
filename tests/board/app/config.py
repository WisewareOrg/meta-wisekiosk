"""The config the WiseKiosk app runs with."""

import os

from board.part import Part, invalid_if


class Config(Part):
    """The config the WiseKiosk app on the board runs with, and the image default it is reseeded from.

    Attributes:
        LIVE_PATH: the live config on the board.
    """

    LIVE_PATH = "/data/config/config.json"
    _DEFAULT_PATH = "/usr/share/wisekiosk/config.example.json"

    def sha256(self) -> str | None:
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

    def sha256_to_keep(self) -> str:
        """Read the sha256 of the live config, which a fault must leave unchanged.

        Returns:
            The hash; the check is invalid if a loss of the config could not show.
        """
        live = self.sha256()
        with invalid_if("a loss of the board's config could not show"):
            assert shows_a_loss(live, self.default_sha256())
        return live

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


def shows_a_loss(live: str | None, default: str | None) -> bool:
    """Whether losing the live config, and reseeding the image default, would show as a change.

    Args:
        live: the live config's sha256, None if it was missing.
        default: the image default's sha256, None if it was missing.

    Returns:
        False if the board held no config, or held the image default, or the default is unreadable.
    """
    return live is not None and default is not None and live != default
