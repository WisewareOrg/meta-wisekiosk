"""The board's screen: its X server, the windows and mode it shows, and what the panel shows."""

import re
import time
from typing import TYPE_CHECKING

from labgrid.driver.exception import ExecutionError

from board.part import Part
from board.screen.layout import WindowLayout

if TYPE_CHECKING:
    from board import Board

_LAYOUT_SEPARATOR = "=== windows"
_LAYOUT_READ = (
    "DISPLAY=:0 xrandr --current; "
    f"echo '{_LAYOUT_SEPARATOR}'; "
    "for id in $(DISPLAY=:0 xwininfo -root -children | awk '/^ +0x/ {print $1}'); do "
    'echo "=== $id"; DISPLAY=:0 xwininfo -id "$id"; done'
)
_MODE = re.compile(r"^(\d+)x(\d+)")
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
    """

    def __init__(self, board: "Board") -> None:
        """Bind to the board, with no grab taken.

        Args:
            board: the board under test.
        """
        super().__init__(board)
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

    def x_server_options(self) -> list[str]:
        """Read the options the one X server running was started with.

        Returns:
            Its command line's arguments, the program first.
        """
        pids = self._board.run("pidof Xorg").text.split()
        assert len(pids) == 1, f"not one X server running: {pids}"
        return self._board.run(f"tr '\\0' '\\n' < /proc/{pids[0]}/cmdline", check=True).stdout

    def window_layout(self) -> WindowLayout:
        """Read the outputs X drives and its top-level windows, in one command.

        Returns:
            The layout, with the read's raw text.
        """
        lines = self._board.run(_LAYOUT_READ, check=True).stdout
        split = lines.index(_LAYOUT_SEPARATOR)
        return WindowLayout.parse(lines[:split], lines[split + 1 :])

    def mode(self) -> tuple[int, int]:
        """Read the display mode the panel is driven at.

        Returns:
            Its width and height, from the one mode `xrandr` marks current.
        """
        current = [
            line.strip() for line in self._board.run("DISPLAY=:0 xrandr --current", check=True).stdout if "*" in line
        ]
        assert len(current) == 1, f"not one current mode: {current}"
        mode = _MODE.match(current[0])
        assert mode, f"the current mode is unreadable: {current[0]!r}"
        return int(mode[1]), int(mode[2])

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

        The first good grab reads the screen's size, and registers the picture's removal for when the test
        ends.

        Returns:
            The sha256 of the grab before and of this one, each None for a bad grab or none.

        Raises:
            ExecutionError: X did not report the screen's size, as while it starts; a wait takes it as a read
                that does not hold.
        """
        if self._crop is None:
            xdpyinfo = self._board.run("DISPLAY=:0 xdpyinfo")
            dimensions = _DIMENSIONS.search(xdpyinfo.text) if xdpyinfo.returncode == 0 else None
            if dimensions is None:
                raise ExecutionError("DISPLAY=:0 xdpyinfo", xdpyinfo.stdout, xdpyinfo.stderr)
            self._board.cleanup.callback(self._board.run, f"rm -f {_GRAB_PATH}")
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
