"""Target suite: the panel shows only the instance, at the minimum resolution."""

import re
from collections.abc import Callable

from board import Board
from panel import Panel

# TST031's floor
_MIN_WIDTH = 1280
_MIN_HEIGHT = 720

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


def _windows(lines: list[str]) -> list[dict]:
    """One dict per `xwininfo -id` block in `lines`, in the order read.

    Args:
        lines: the output lines of the `xwininfo -id` walk.

    Returns:
        For each window its id, name, the integer fields of `_INT_FIELDS` and `map_state`.
    """
    windows = []
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
    return windows


def _overlaps(window: dict, panel_area: dict) -> bool:
    """Whether `window`'s outer rectangle, border included, overlaps `panel_area` with positive area.

    Args:
        window: a window from `_windows`.
        panel_area: the panel's x, y, width and height.

    Returns:
        True if the two rectangles overlap with positive area.
    """
    left = window["x"] - window["border"]
    top = window["y"] - window["border"]
    right = window["x"] + window["width"] + window["border"]
    bottom = window["y"] + window["height"] + window["border"]
    return (
        left < panel_area["x"] + panel_area["width"]
        and right > panel_area["x"]
        and top < panel_area["y"] + panel_area["height"]
        and bottom > panel_area["y"]
    )


def test_pointer_display_disabled(board: Board, panel: Panel, record_property: Callable[[str, object], None]) -> None:
    """TST013 pointer display disabled: read X's start-up options and require `-nocursor`.

    Args:
        board: the board under test, whose X server's command line is read.
        panel: the probe in the browser, waited on so the instance is on the panel.
        record_property: records the requirement and X's command line.

    Raises:
        AssertionError: X is not running, more than one X runs, or X runs without `-nocursor`.
    """
    record_property("requirement", "TST013")
    panel.wait_on_panel()

    pids = board.run("pidof Xorg")[0]
    pids = " ".join(pids).split()
    assert pids, "X is not running"
    assert len(pids) == 1, f"more than one X: {pids}"
    stdout, _stderr, _returncode = board.run(f"tr '\\0' '\\n' < /proc/{pids[0]}/cmdline", check=True)
    record_property("x_cmdline", "\n".join(stdout))

    assert "-nocursor" in stdout, f"X runs without -nocursor: {stdout}"


def test_instance_covers_the_panel(board: Board, panel: Panel, record_property: Callable[[str, object], None]) -> None:
    """TST030 instance covers the panel: its window contains the panel and nothing shown overlies it.

    Args:
        board: the board under test, whose X windows are read.
        panel: the probe in the browser, waited on so the instance is on the panel.
        record_property: records the requirement, the xrandr output and the window layout.

    Raises:
        AssertionError: the layout is unreadable, the instance's window is not the one viewable
            window covering the panel, or a shown window overlies it.
    """
    record_property("requirement", "TST030")
    panel.wait_on_panel()

    stdout, _stderr, _returncode = board.run(_LAYOUT_READ, check=True)
    split = stdout.index(_SEPARATOR)
    xrandr, window_lines = stdout[:split], stdout[split + 1 :]
    record_property("xrandr", "\n".join(xrandr))
    record_property("window_layout", "\n".join(window_lines))

    connected = [match for match in map(_CONNECTED.match, xrandr) if match]
    assert connected, "no connected output with a mode"
    assert len(connected) == 1, f"more than one connected output: {[m.group(0) for m in connected]}"
    width, height, x, y = (int(group) for group in connected[0].groups())
    panel_area = {"x": x, "y": y, "width": width, "height": height}

    windows = _windows(window_lines)
    instances = [index for index, window in enumerate(windows) if "WK1 " in window["name"]]
    assert instances, "no window carries the instance's title"
    assert len(instances) == 1, (
        f"more than one window carries the instance's title: {[windows[i]['id'] for i in instances]}"
    )
    instance = windows[instances[0]]
    assert instance["map_state"] == "IsViewable", f"the instance's window is {instance['map_state']}"

    contains = (
        instance["x"] <= panel_area["x"]
        and instance["y"] <= panel_area["y"]
        and instance["x"] + instance["width"] >= panel_area["x"] + panel_area["width"]
        and instance["y"] + instance["height"] >= panel_area["y"] + panel_area["height"]
    )
    assert contains, (
        f"the instance's window {instance['width']}x{instance['height']}+{instance['x']}+{instance['y']} "
        f"does not contain the panel {width}x{height}+{x}+{y}"
    )

    for above in windows[: instances[0]]:
        assert above["map_state"] != "IsViewable" or not _overlaps(above, panel_area), (
            f"window {above['id']} {above['name']!r} "
            f"{above['width']}x{above['height']}+{above['x']}+{above['y']} is shown above the instance "
            f"and overlaps the panel"
        )


def test_minimum_resolution(board: Board, panel: Panel, record_property: Callable[[str, object], None]) -> None:
    """TST031 minimum resolution: the display mode and the page's layout size are each at least 1280x720.

    Args:
        board: the board under test, whose current display mode is read.
        panel: the probe in the browser, whose sample carries the page's layout size.
        record_property: records the requirement, the layout and the xrandr output.

    Raises:
        AssertionError: the mode or the layout is unreadable, or either is below the floor.
    """
    record_property("requirement", "TST031")
    _uptime_s, sample = panel.wait_on_panel()
    record_property("layout", sample["layout"])

    xrandr = board.read("DISPLAY=:0 xrandr --current")
    record_property("xrandr", xrandr)
    current = [line.strip() for line in xrandr.splitlines() if "*" in line]
    assert current, "xrandr reports no current mode"
    assert len(current) == 1, f"more than one current mode: {current}"
    mode = re.match(r"^(\d+)x(\d+)", current[0])
    assert mode, f"xrandr's current mode line is unreadable: {current[0]!r}"

    layout = re.match(r"^(\d+)x(\d+)$", sample["layout"])
    assert layout, f"the probe's layout is unreadable: {sample['layout']!r}"

    mode_width, mode_height = int(mode.group(1)), int(mode.group(2))
    layout_width, layout_height = int(layout.group(1)), int(layout.group(2))
    assert mode_width >= _MIN_WIDTH, f"display mode width {mode_width} is below {_MIN_WIDTH}"
    assert mode_height >= _MIN_HEIGHT, f"display mode height {mode_height} is below {_MIN_HEIGHT}"
    assert layout_width >= _MIN_WIDTH, f"layout width {layout_width} is below {_MIN_WIDTH}"
    assert layout_height >= _MIN_HEIGHT, f"layout height {layout_height} is below {_MIN_HEIGHT}"
