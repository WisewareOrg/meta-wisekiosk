"""Target suite: the panel shows only the instance, at the minimum resolution."""

import re

# TST031's floor
MIN_WIDTH = 1280
MIN_HEIGHT = 720

_SEPARATOR = "=== windows"
_LAYOUT_READ = (
    "DISPLAY=:0 xrandr --current; "
    f"echo '{_SEPARATOR}'; "
    "for id in $(DISPLAY=:0 xwininfo -root -children | awk '/^ +0x/ {print $1}'); do "
    'echo "=== $id"; DISPLAY=:0 xwininfo -id "$id"; done'
)
_CONNECTED = re.compile(r"^\S+ connected (?:primary )?(\d+)x(\d+)\+(\d+)\+(\d+)")
_WINDOW_ID = re.compile(r'^xwininfo: Window id: (0x[0-9a-fA-F]+)(?: "(.*)"| \(has no name\))?$')
_FIELDS = {
    "x": re.compile(r"^\s*Absolute upper-left X:\s+(-?\d+)"),
    "y": re.compile(r"^\s*Absolute upper-left Y:\s+(-?\d+)"),
    "width": re.compile(r"^\s*Width:\s+(\d+)"),
    "height": re.compile(r"^\s*Height:\s+(\d+)"),
    "border": re.compile(r"^\s*Border width:\s+(\d+)"),
    "map_state": re.compile(r"^\s*Map State:\s+(\w+)"),
}


def _x_pid(board):
    """The pid of the one running X server."""
    stdout, _stderr, _returncode = board.run("pidof Xorg", check=True)
    pids = " ".join(stdout).split()
    assert pids, "X is not running"
    assert len(pids) == 1, f"more than one X: {pids}"
    return pids[0]


def _windows(lines):
    """One dict per `xwininfo -id` block in `lines`, in the order read: id, name and `_FIELDS`."""
    windows = []
    for line in lines:
        header = _WINDOW_ID.match(line)
        if header:
            windows.append({"id": header.group(1), "name": header.group(2) or ""})
            continue
        for key, pattern in _FIELDS.items():
            match = windows and pattern.match(line)
            if match:
                windows[-1][key] = match.group(1) if key == "map_state" else int(match.group(1))
    return windows


def _overlaps(window, panel):
    """Whether `window`'s outer rectangle, border included, overlaps `panel` with positive area."""
    left = window["x"] - window["border"]
    top = window["y"] - window["border"]
    right = window["x"] + window["width"] + window["border"]
    bottom = window["y"] + window["height"] + window["border"]
    return (
        left < panel["x"] + panel["width"]
        and right > panel["x"]
        and top < panel["y"] + panel["height"]
        and bottom > panel["y"]
    )


def test_pointer_display_disabled(board, panel, record_property):
    """TST013 pointer display disabled: read X's start-up options and require `-nocursor`."""
    record_property("requirement", "TST013")
    panel.wait_on_panel()

    pid = _x_pid(board)
    stdout, _stderr, _returncode = board.run(
        f"tr '\\0' '\\n' < /proc/{pid}/cmdline", check=True
    )
    record_property("x_cmdline", "\n".join(stdout))

    assert "-nocursor" in stdout, f"X runs without -nocursor: {stdout}"


def test_instance_covers_the_panel(board, panel, record_property):
    """TST030 instance covers the panel: its window contains the panel and nothing shown overlies it."""
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
    assert len(instances) == 1, f"more than one window carries the instance's title: {instances}"
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


def test_minimum_resolution(board, panel, record_property):
    """TST031 minimum resolution: the display mode and the page's layout size are each at least 1280x720."""
    record_property("requirement", "TST031")
    _uptime_s, sample = panel.wait_on_panel()

    stdout, _stderr, _returncode = board.run("DISPLAY=:0 xrandr --current", check=True)
    record_property("xrandr", "\n".join(stdout))
    current = [line.strip() for line in stdout if "*" in line]
    assert current, "xrandr reports no current mode"
    mode = re.match(r"^(\d+)x(\d+)", current[0])
    assert mode, f"xrandr's current mode line is unreadable: {current[0]!r}"

    layout = re.match(r"^(\d+)x(\d+)$", sample["layout"])
    assert layout, f"the probe's layout is unreadable: {sample['layout']!r}"
    record_property("layout", sample["layout"])

    mode_width, mode_height = int(mode.group(1)), int(mode.group(2))
    layout_width, layout_height = int(layout.group(1)), int(layout.group(2))
    assert mode_width >= MIN_WIDTH, f"display mode width {mode_width} is below {MIN_WIDTH}"
    assert mode_height >= MIN_HEIGHT, f"display mode height {mode_height} is below {MIN_HEIGHT}"
    assert layout_width >= MIN_WIDTH, f"layout width {layout_width} is below {MIN_WIDTH}"
    assert layout_height >= MIN_HEIGHT, f"layout height {layout_height} is below {MIN_HEIGHT}"
