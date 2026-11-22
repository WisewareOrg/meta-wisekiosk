"""The X server and the output it drives."""

import re
from typing import NamedTuple

from board.part import Part

_SEPARATOR = "=== windows"
_LAYOUT_READ = (
    "DISPLAY=:0 xrandr --current; "
    f"echo '{_SEPARATOR}'; "
    "for id in $(DISPLAY=:0 xwininfo -root -children | awk '/^ +0x/ {print $1}'); do "
    'echo "=== $id"; DISPLAY=:0 xwininfo -id "$id"; done'
)
_CONNECTED = re.compile(r"^\S+ connected (?:primary )?(\d+)x(\d+)\+(\d+)\+(\d+)")
_WINDOW_ID = re.compile(r'^xwininfo: Window id: (0x[0-9a-fA-F]+)(?: "(.*)"| \(has no name\))?$')
_INT_FIELDS = {
    "x": re.compile(r"^\s*Absolute upper-left X:\s+(-?\d+)"),
    "y": re.compile(r"^\s*Absolute upper-left Y:\s+(-?\d+)"),
    "width": re.compile(r"^\s*Width:\s+(\d+)"),
    "height": re.compile(r"^\s*Height:\s+(\d+)"),
    "border": re.compile(r"^\s*Border width:\s+(\d+)"),
}
_MAP_STATE = re.compile(r"^\s*Map State:\s+(\w+)")
_MODE = re.compile(r"^(\d+)x(\d+)")
_SCREEN_SAVER_TIMEOUT = re.compile(r"timeout:\s+(\d+)")
# power management is off when it is disabled, or the server has no such extension
_DPMS_OFF = ("DPMS is Disabled", "Server does not have the DPMS Extension")


class Area(NamedTuple):
    """A rectangle on the screen.

    Attributes:
        x: its left edge.
        y: its top edge.
        width: its width.
        height: its height.
    """

    x: int
    y: int
    width: int
    height: int


class Window(NamedTuple):
    """One top-level window, as `xwininfo -id` reports it.

    Attributes:
        id: the window's id.
        name: the window's title, empty if it has none.
        x: its left edge, inside its border.
        y: its top edge, inside its border.
        width: its width, inside its border.
        height: its height, inside its border.
        border: its border's width.
        map_state: how X maps it; `IsViewable` is shown.
    """

    id: str
    name: str
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    border: int | None = None
    map_state: str | None = None

    def overlaps(self, area: Area) -> bool:
        """Whether the window's outer rectangle, border included, overlaps `area` with positive area.

        Args:
            area: the rectangle to compare with.

        Returns:
            True if they overlap.
        """
        left = self.x - self.border
        top = self.y - self.border
        right = self.x + self.width + self.border
        bottom = self.y + self.height + self.border
        return left < area.x + area.width and right > area.x and top < area.y + area.height and bottom > area.y

    def contains(self, area: Area) -> bool:
        """Whether the window, inside its border, contains `area`.

        Args:
            area: the rectangle to compare with.

        Returns:
            True if it does.
        """
        return (
            self.x <= area.x
            and self.y <= area.y
            and self.x + self.width >= area.x + area.width
            and self.y + self.height >= area.y + area.height
        )


class WindowLayout(NamedTuple):
    """The outputs X drives and its top-level windows, from one read.

    Attributes:
        outputs: each connected output that has a mode, as the area it covers.
        windows: the top-level windows, in the order X lists them.
        xrandr: `xrandr --current`'s output.
        windows_text: `xwininfo`'s output for each window.
    """

    outputs: list[Area]
    windows: list[Window]
    xrandr: str
    windows_text: str


class CurrentMode(NamedTuple):
    """The display's current mode, as `xrandr --current` reports it.

    Attributes:
        xrandr: `xrandr --current`'s output.
        lines: the lines that mark a mode current.
        width: the first such line's width, None if it is unreadable or there is none.
        height: the first such line's height, None if it is unreadable or there is none.
    """

    xrandr: str
    lines: list[str]
    width: int | None
    height: int | None


class Display(Part):
    """The X server on the board, and the output it drives."""

    def x_server_options(self) -> list[str]:
        """Read the X server's command line.

        Asserts there is exactly one X server running.

        Returns:
            Its arguments, the program first.
        """
        pids = " ".join(self._board.run("pidof Xorg").stdout).split()
        assert pids, "X is not running"
        assert len(pids) == 1, f"more than one X: {pids}"
        return self._board.run(f"tr '\\0' '\\n' < /proc/{pids[0]}/cmdline", check=True).stdout

    def window_layout(self) -> WindowLayout:
        """Read the outputs X drives and its top-level windows, in one command.

        Returns:
            The layout, with the raw text of both reads.
        """
        stdout = self._board.run(_LAYOUT_READ, check=True).stdout
        split = stdout.index(_SEPARATOR)
        xrandr, window_lines = stdout[:split], stdout[split + 1 :]
        outputs = [
            Area(int(x), int(y), int(width), int(height))
            for width, height, x, y in (match.groups() for match in map(_CONNECTED.match, xrandr) if match)
        ]
        return WindowLayout(outputs, self._parse_windows(window_lines), "\n".join(xrandr), "\n".join(window_lines))

    def mode(self) -> CurrentMode:
        """Read the display's current mode.

        Returns:
            The mode, with `xrandr`'s raw output.
        """
        stdout = self._board.run("DISPLAY=:0 xrandr --current", check=True).stdout
        current = [line.strip() for line in stdout if "*" in line]
        mode = _MODE.match(current[0]) if current else None
        width, height = (int(mode.group(1)), int(mode.group(2))) if mode else (None, None)
        return CurrentMode("\n".join(stdout), current, width, height)

    def xset_query(self) -> tuple[str, int | None, bool]:
        """Read the X server's settings with `xset q`.

        Returns:
            `xset q`'s raw output; the screen saver's timeout in seconds, None if the output carries none;
            then whether display power management is off, disabled or absent from the server.
        """
        text = "\n".join(self._board.run("DISPLAY=:0 xset q", check=True).stdout)
        timeout = _SCREEN_SAVER_TIMEOUT.search(text)
        return text, int(timeout.group(1)) if timeout else None, any(off in text for off in _DPMS_OFF)

    @staticmethod
    def _parse_windows(lines: list[str]) -> list[Window]:
        """One window per `xwininfo -id` block in `lines`, in the order read.

        Args:
            lines: `xwininfo`'s output for each window.

        Returns:
            The windows.
        """
        windows: list[dict] = []
        for line in lines:
            header = _WINDOW_ID.match(line)
            if header:
                windows.append({"id": header.group(1), "name": header.group(2) or ""})
                continue
            for key, pattern in _INT_FIELDS.items():
                match = pattern.match(line)
                if match:
                    windows[-1][key] = int(match.group(1))
            match = _MAP_STATE.match(line)
            if match:
                windows[-1]["map_state"] = match.group(1)
        return [Window(**window) for window in windows]
