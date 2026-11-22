"""wisekiosk.service, the WiseKiosk app's backend."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from board import Board


class Backend:
    """wisekiosk.service on the board: its mask for this boot, and its release.

    Each change registers its undo on the board's cleanup once it has taken.
    """

    _RELEASE = "systemctl unmask --runtime wisekiosk.service; systemctl start wisekiosk.service"
    _RELEASE_UNIT = "test-backend-release"

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board

    def mask(self) -> None:
        """Mask the backend for this boot only; when the test ends it is unmasked and started."""
        self._board.cleanup.callback(self.unmask_and_wait_for_page)
        self._board.run("systemctl mask --runtime wisekiosk.service", check=True)

    def unit_state(self) -> tuple[list[str], list[str]]:
        """What systemd says of the backend's unit.

        Returns:
            The stdout lines of `systemctl is-enabled` and of `systemctl is-active` for it.
        """
        enabled = self._board.run("systemctl is-enabled wisekiosk.service")[0]
        active = self._board.run("systemctl is-active wisekiosk.service")[0]
        return enabled, active

    def unmask_and_start(self) -> None:
        """Unmask and start the backend, without waiting for the page."""
        self._board.run(self._RELEASE, check=True)

    def unmask_and_wait_for_page(self) -> None:
        """Unmask and start the backend, then wait for the page; idempotent, so it may be registered twice."""
        self.unmask_and_start()
        self._board.wait_for_page()

    def unmask_and_start_after(self, seconds: float) -> None:
        """Have a board-side timer unmask and start the backend in `seconds`, whatever the host does.

        Args:
            seconds: the timer's delay.
        """
        self._board.run_later(self._RELEASE_UNIT, seconds, f"/bin/sh -c '{self._RELEASE}'")
