"""The board's screen: the mode it is driven at and the planes it shows, as the kernel's display driver reports them."""

import re
from typing import NamedTuple

from board.part import Part

_STATE = "/sys/kernel/debug/dri/0/state"
_DPMS = "/sys/class/drm/card0-HDMI-A-1/dpms"
_CONSOLE_BLANK = "/sys/module/kernel/parameters/consoleblank"
_PLANE = re.compile(r"^plane\[\d+\].*?(?=^plane\[|^crtc\[)", re.MULTILINE | re.DOTALL)
_MODE = re.compile(r'mode: "(\d+)x(\d+)"')
_READS = 12
_READ_EVERY_US = 250_000


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

    A program that draws puts a new buffer on the screen for each frame, so a screen showing more than
    one buffer over 3 s is changing, and one showing a single buffer stands still.
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

    def mode(self) -> tuple[int, int]:
        """Read the display mode the panel is driven at.

        Returns:
            Its width and height.
        """
        mode = _MODE.search(self._state())
        assert mode, "the panel is driven at no mode"
        return int(mode[1]), int(mode[2])

    def is_changing(self) -> bool:
        """Read the buffer on the screen over 3 s, and say whether it changed.

        Returns:
            True if it did.
        """
        return len(self._buffers()) > 1

    def stands_still(self) -> bool:
        """Read the buffer on the screen over 3 s, and say whether it stayed the same.

        Returns:
            True if it did.
        """
        return len(self._buffers()) == 1

    def _buffers(self) -> set[str]:
        """Read the buffer on the screen 12 times, a quarter second apart.

        Returns:
            The buffers seen; `0` is none.
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
