"""The board's screen: the X server's settings, and what the panel shows."""

import re
import time
from typing import TYPE_CHECKING

from board.part import Part
from board.screen.display import Display

if TYPE_CHECKING:
    from board import Board

_GRAB_PATH = "/tmp/kiosk-grab.png"
_GRAB_EVERY_SECONDS = 5
# below this an import that returned 0 did not write a picture (kiosk-render-check.sh)
_MIN_PNG_BYTES = 100
_DIMENSIONS = re.compile(r"dimensions:\s+(\d+)x(\d+)")
_SCREEN_SAVER_TIMEOUT = re.compile(r"timeout:\s+(\d+)")
# power management is off when it is disabled, or the server has no such extension
_DPMS_OFF = ("DPMS is Disabled", "Server does not have the DPMS Extension")


class Screen(Part):
    """The board's screen, read from its X server.

    What the panel shows is read as grabs of its middle third, at least 5 s apart; two good grabs in
    a row either differ (the panel is changing) or match (it stands still).

    Attributes:
        display: the X server and the output it drives.
    """

    display: Display

    def __init__(self, board: "Board") -> None:
        """Bind to the board, with no grab taken.

        Args:
            board: the board under test.
        """
        super().__init__(board)
        self.display = Display(board)
        self._crop: str | None = None
        self._last_grab: str | None = None
        self._next_grab_at = 0.0

    def blanking(self) -> tuple[int | None, bool]:
        """Read the X server's blanking settings.

        Returns:
            The screen saver's timeout in seconds (None if `xset q` shows none), and whether display power
            management is enabled.
        """
        settings = self._board.run("DISPLAY=:0 xset q", check=True).text
        timeout = _SCREEN_SAVER_TIMEOUT.search(settings)
        return (int(timeout[1]) if timeout else None), not any(off in settings for off in _DPMS_OFF)

    def is_changing(self) -> bool:
        """Grab the panel, and say whether it differs from the grab before.

        Returns:
            True if both grabs are good and differ.
        """
        before, now = self._grab()
        return None not in (before, now) and before != now

    def stands_still(self) -> bool:
        """Grab the panel, and say whether it matches the grab before.

        Returns:
            True if both grabs are good and match.
        """
        before, now = self._grab()
        return now is not None and before == now

    def _grab(self) -> tuple[str | None, str | None]:
        """Grab the panel's middle third, once 5 s have passed since the grab before.

        The first grab reads the screen's size, and registers the picture's removal for when the test ends.

        Returns:
            The sha256 of the grab before and of this one, each None for a bad grab or none.
        """
        if self._crop is None:
            self._board.cleanup.callback(self._board.run, f"rm -f {_GRAB_PATH}")
            dimensions = _DIMENSIONS.search(self._board.run("DISPLAY=:0 xdpyinfo", check=True).text)
            assert dimensions, "xdpyinfo reported no screen dimensions"
            width, height = int(dimensions[1]), int(dimensions[2])
            self._crop = f"{width}x{height // 3}+0+{height // 3}"
        time.sleep(max(0.0, self._next_grab_at - time.monotonic()))
        self._next_grab_at = time.monotonic() + _GRAB_EVERY_SECONDS
        grab = self._board.run(
            f"rm -f {_GRAB_PATH}; DISPLAY=:0 import -window root -crop {self._crop} +repage {_GRAB_PATH} && "
            f"[ $(stat -c %s {_GRAB_PATH}) -ge {_MIN_PNG_BYTES} ] && sha256sum {_GRAB_PATH}"
        )
        before, self._last_grab = self._last_grab, grab.text.split()[0] if grab.returncode == 0 else None
        return before, self._last_grab
