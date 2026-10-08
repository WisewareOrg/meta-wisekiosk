"""Specifies cases/kiosk_layout/verdict.py: the mode `DISPLAY=:0 xrandr` reports, judged against
the 720p floor (the ticket's "Decided": the display runs at the configured mode, at or above the
design floor).

Pure: no device, no DOM -- every mode string and xrandr dump is a plain Python value.
"""

_MIN_WIDTH = 1280
_MIN_HEIGHT = 720


def verdict(mode):
    """("ok"|"error", reason) against the 720p floor. `mode` is an
    "<w>x<h>" mode string, the same shape pick_below_floor_mode's own
    `current`/candidate return values and xrandr's own mode token carry."""
    width_str, _, height_str = mode.partition("x")
    width, height = int(width_str), int(height_str)
    if width < _MIN_WIDTH:
        return "error", f"width {width} is below the {_MIN_WIDTH} floor"
    if height < _MIN_HEIGHT:
        return "error", f"height {height} is below the {_MIN_HEIGHT} floor"
    return "ok", ""


def pick_below_floor_mode(xrandr_output):
    """The connected output's own name, its current mode, and the largest
    mode (by area) that output offers below the 720p floor (None if it
    offers none) -- from `DISPLAY=:0 xrandr`'s own shape: a "<name>
    connected ..." header line names the active connector, and each
    following indented "<w>x<h> ..." line names one of its modes, the
    current one carrying a "*" against one of its refresh rates."""
    connector = None
    current = None
    below_floor = []
    for line in xrandr_output.splitlines():
        if " connected " in line:
            connector = line.split()[0]
            continue
        if connector is None or not line.startswith(" "):
            continue
        parts = line.split()
        if not parts or "x" not in parts[0]:
            continue
        w_str, _, h_str = parts[0].partition("x")
        if not (w_str.isdigit() and h_str.isdigit()):
            continue
        width, height = int(w_str), int(h_str)
        if "*" in line:
            current = parts[0]
        if width < _MIN_WIDTH or height < _MIN_HEIGHT:
            below_floor.append((width, height))

    candidate = None
    if below_floor:
        best = max(below_floor, key=lambda mode: mode[0] * mode[1])
        candidate = f"{best[0]}x{best[1]}"
    return connector, current, candidate
