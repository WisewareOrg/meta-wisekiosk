"""Screenshots of the panel's middle third, where the clock config's seconds sit."""

import re
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from board import Board

_CAPTURE_PATH = "/tmp/tst005.png"
_DIMENSIONS = re.compile(r"dimensions:\s+(\d+)x(\d+)")
_CAPTURE_EVERY_SECONDS = 5
# below this an import that returned 0 did not write a picture (kiosk-render-check.sh)
_MIN_PNG_BYTES = 100


class Captures:
    """The panel's middle third grabbed every 5 s, and the series the grabs make.

    A capture is `(board uptime just before the grab, sha256 | None)`; a None hash is a bad capture.
    A read is two good captures in a row, and is changing when their hashes differ.

    Attributes:
        taken: every capture taken, in order.
        changing_run: how many changing reads end at the latest capture.
    """

    taken: list[tuple[float | None, str | None]]
    changing_run: int

    def __init__(self, board: "Board") -> None:
        """Bind to the board, with no capture taken.

        Args:
            board: the board under test.
        """
        self._board = board
        self._crop: str | None = None
        self._next_at = time.monotonic()
        self.taken = []
        self.changing_run = 0

    @property
    def crop(self) -> str:
        """The root window's middle third, as `WxH+X+Y`, read from xdpyinfo on first use.

        Returns:
            The crop.
        """
        if self._crop is None:
            match = _DIMENSIONS.search(self._board.run("DISPLAY=:0 xdpyinfo", check=True).text)
            assert match is not None, "xdpyinfo reported no screen dimensions"
            width, height = int(match.group(1)), int(match.group(2))
            self._crop = f"{width}x{height // 3}+0+{height // 3}"
        return self._crop

    def take(self) -> tuple[float | None, str | None]:
        """Wait out the 5 s cadence, grab once, and add the capture to `taken`, updating `changing_run`.

        The first grab registers the picture's removal for when the test ends.

        Returns:
            The board uptime just before the grab and the picture's sha256; both None if the grab
            timed out, the hash alone None if no picture was written.
        """
        if not self.taken:
            self._board.cleanup.callback(self._board.run, f"rm -f {_CAPTURE_PATH}")
        time.sleep(max(0, self._next_at - time.monotonic()))
        self._next_at = time.monotonic() + _CAPTURE_EVERY_SECONDS
        capture = self._grab()
        previous = self.taken[-1] if self.taken else (None, None)
        if capture[1] is not None and previous[1] is not None and capture[1] != previous[1]:
            self.changing_run += 1
        else:
            self.changing_run = 0
        self.taken.append(capture)
        return capture

    def stood_still(self) -> bool:
        """Whether the latest read is a pair of good captures with the same hash.

        Returns:
            True if the last two captures are good and equal.
        """
        return len(self.taken) >= 2 and self.taken[-1][1] is not None and self.taken[-1][1] == self.taken[-2][1]

    def _grab(self) -> tuple[float | None, str | None]:
        """Grab the crop once.

        Returns:
            The board uptime just before the grab and the picture's sha256, as `take` returns them.
        """
        cmd = (
            f"rm -f {_CAPTURE_PATH}; cat /proc/uptime; "
            f"DISPLAY=:0 import -window root -crop {self.crop} +repage {_CAPTURE_PATH}; "
            f"echo rc=$?; stat -c %s {_CAPTURE_PATH}; sha256sum {_CAPTURE_PATH}"
        )
        try:
            stdout = self._board.run(cmd).stdout
        except subprocess.TimeoutExpired:
            return None, None
        uptime_s = float(stdout[0].split()[0])
        good = len(stdout) >= 4 and stdout[1] == "rc=0" and int(stdout[2]) >= _MIN_PNG_BYTES
        return uptime_s, stdout[3].split()[0] if good else None
