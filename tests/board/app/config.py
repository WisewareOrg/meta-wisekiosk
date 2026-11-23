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

    def confirm_a_loss_would_show(self, before: str | None) -> None:
        """Fail the check as invalid if the config held before a fault could not show its loss.

        Args:
            before: the live config's sha256 before the fault, None if it was missing.
        """
        with invalid_if("a loss of the board's config could not show"):
            assert shows_a_loss(before, self.default_sha256())

    def use(self, path: str | os.PathLike[str]) -> None:
        """Swap the app onto `path`'s config, and leave the instance running against it, until the test ends.

        When the test ends the browser stops, the config is unmounted, the backend restarts onto the live
        config, and the browser starts again: the backend's restart is registered before the bind mount,
        so it runs after the unmount.

        Args:
            path: the config file on the host.
        """
        app = self._board.app
        app.kiosk.stop()
        self._board.cleanup.callback(app.kiosk.start)
        self._board.cleanup.callback(self._restart_backend_and_wait)
        self._board.bind_over(path, self.LIVE_PATH)
        app.backend.restart()
        self._board.seconds_until(app.is_served)
        app.kiosk.start()
        self._board.cleanup.callback(app.kiosk.stop)

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
        self._board.app.backend.restart()
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
