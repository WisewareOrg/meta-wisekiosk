"""The window layout the X server reports: the panel's outputs and the top-level windows above it."""

import re
from typing import NamedTuple

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

    @property
    def shown(self) -> bool:
        """Whether X shows the window.

        Returns:
            True if it is viewable.
        """
        return self.map_state == "IsViewable"

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
        windows: the top-level windows, in the order X lists them, top first.
        text: the read's raw output: `xrandr --current`, then `xwininfo` for each window.
    """

    outputs: list[Area]
    windows: list[Window]
    text: str

    @classmethod
    def parse(cls, xrandr: list[str], window_lines: list[str]) -> "WindowLayout":
        """Parse a read of the outputs and the windows.

        Args:
            xrandr: `xrandr --current`'s lines.
            window_lines: `xwininfo -id`'s lines for each window, each block headed by its id line.

        Returns:
            The layout.
        """
        outputs = [
            Area(int(x), int(y), int(width), int(height))
            for width, height, x, y in (match.groups() for match in map(_CONNECTED.match, xrandr) if match)
        ]
        windows: list[dict] = []
        for line in window_lines:
            header = _WINDOW_ID.match(line)
            if header:
                windows.append({"id": header[1], "name": header[2] or ""})
                continue
            for key, pattern in _INT_FIELDS.items():
                if match := pattern.match(line):
                    windows[-1][key] = int(match[1])
            if match := _MAP_STATE.match(line):
                windows[-1]["map_state"] = match[1]
        return cls(outputs, [Window(**window) for window in windows], "\n".join(xrandr + window_lines))

    @property
    def panel(self) -> Area:
        """The panel: the one connected output with a mode.

        Returns:
            Its area.
        """
        assert len(self.outputs) == 1, f"not one connected output with a mode: {self.outputs}"
        return self.outputs[0]

    @property
    def instance(self) -> Window:
        """The instance's window: the one carrying the probe's title.

        Returns:
            The window.
        """
        instances = [window for window in self.windows if "WK1 " in window.name]
        assert len(instances) == 1, f"not one window carries the instance's title: {instances}"
        return instances[0]

    def above(self, window: Window) -> list[Window]:
        """The windows stacked above `window`.

        Args:
            window: one of the layout's windows.

        Returns:
            The windows X lists before it.
        """
        return self.windows[: self.windows.index(window)]
