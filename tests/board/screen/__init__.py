"""The board's screen: the mode it is driven at and the planes it shows, as the kernel's display driver reports them."""

import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

from board.part import Part, invalid_if

_STATE = "/sys/kernel/debug/dri/0/state"
_DPMS = "/sys/class/drm/card0-HDMI-A-1/dpms"
_CONSOLE_BLANK = "/sys/module/kernel/parameters/consoleblank"
_PLANE = re.compile(r"^plane\[\d+\].*?(?=^plane\[|^crtc\[)", re.MULTILINE | re.DOTALL)
_MODE = re.compile(r'mode: "(\d+)x(\d+)"')
_NO_BUFFER = "fb=0"
_READS = 12
_READ_EVERY_US = 250_000
_PICTURES_APART_SECONDS = 5
_PICTURE_TIMEOUT_SECONDS = 60


class Plane(NamedTuple):
    """One plane the screen shows.

    Attributes:
        allocated_by: the program whose buffer it shows.
        position: where it is shown, as `<width>x<height>+<x>+<y>`.
    """

    allocated_by: str
    position: str


class Screen(Part):
    """The board's screen, as the kernel's display driver reports it.

    A program that draws puts a new buffer on the screen for each frame, so a screen showing more than one
    buffer over some seconds is changing buffers, and one showing a single buffer stands still. Which buffer
    it shows does not say what is in it; `picture_changes` reads that.
    """

    def blanking(self) -> tuple[str, int]:
        """Read whether anything blanks the screen.

        Returns:
            The connector's power state, and the console's blanking timeout in seconds (0 for none).
        """
        dpms, console = self._board.run(f"cat {_DPMS} {_CONSOLE_BLANK}", check=True).stdout
        return dpms, int(console)

    def planes(self, state: str | None = None) -> list[Plane]:
        """Read the planes the screen shows.

        Args:
            state: the display driver's state as read earlier; if None, it is read now.

        Returns:
            Each plane with a buffer.
        """
        planes = []
        for match in _PLANE.finditer(self._state() if state is None else state):
            fields = dict(re.findall(r"^\s+([\w -]+?) ?= ?\[?([^\]\n]+)", match[0], re.MULTILINE))
            if fields["fb"] != "0":
                planes.append(Plane(fields["allocated by"], fields["crtc-pos"]))
        return planes

    def shown_by(self, planes: list[Plane] | None = None) -> list[str]:
        """Read whose buffers the screen shows.

        Args:
            planes: planes as read earlier; if None, they are read now.

        Returns:
            The program that allocated each plane's buffer.
        """
        return [plane.allocated_by for plane in (self.planes() if planes is None else planes)]

    def mode(self) -> tuple[int, int]:
        """Read the display mode the panel is driven at.

        Returns:
            Its width and height; 0 and 0 if it is driven at none.
        """
        mode = _MODE.search(self._state())
        return (int(mode[1]), int(mode[2])) if mode else (0, 0)

    def is_changing(self) -> bool:
        """Read the buffer on the screen for some seconds, and say whether it changed.

        Returns:
            True if it did.
        """
        return len(self._buffers()) > 1

    def stands_still(self) -> bool:
        """Read the buffer on the screen for some seconds, and say whether there is one that stayed the same.

        Returns:
            True if it did.
        """
        buffers = self._buffers()
        return len(buffers) == 1 and _NO_BUFFER not in buffers

    def picture_changes(self) -> bool:
        """Take two pictures of the panel some seconds apart, and say whether they differ.

        Returns:
            True if they do.
        """
        before = self._picture()
        time.sleep(_PICTURES_APART_SECONDS)
        return self._picture() != before

    def _picture(self) -> bytes:
        """Take a picture of the panel with `just screenshot`; the check is invalid if it took none.

        Returns:
            The PNG.
        """
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "panel.png"
            tool = subprocess.run(
                ["just", "screenshot", self._board.host, png],
                capture_output=True,
                text=True,
                timeout=_PICTURE_TIMEOUT_SECONDS,
            )
            with invalid_if("the tool took no picture of the panel"):
                assert png.exists(), tool.stderr
            return png.read_bytes()

    def _buffers(self) -> set[str]:
        """Read the buffer on the screen a number of times in a row.

        Returns:
            The `fb=` lines seen; `fb=0` is none.
        """
        reads = " ".join(str(read) for read in range(_READS))
        lines = self._board.run(
            f"for _ in {reads}; do grep -m1 fb= {_STATE}; usleep {_READ_EVERY_US}; done", check=True
        ).stdout
        return {line.strip() for line in lines}

    def _state(self) -> str:
        """Read the display driver's state.

        Returns:
            The text.
        """
        return "\n".join(self._board.run(f"cat {_STATE}", check=True).stdout) + "\n"
