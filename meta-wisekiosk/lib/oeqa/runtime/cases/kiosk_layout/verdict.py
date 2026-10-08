"""The mode `DISPLAY=:0 xrandr` reports, judged against the 720p floor and the launcher's own
configured mode. Pure: no device, no DOM -- every mode string and xrandr dump is a plain value.
"""

MIN_WIDTH = 1280
MIN_HEIGHT = 720


def current_mode(xrandr_output):
    """The connected output's current mode ("<w>x<h>"), from `DISPLAY=:0 xrandr`'s own shape: a
    "<w>x<h> ..." line carrying a "*" against one of its refresh rates names the mode in effect.
    None if no line carries one."""
    for line in xrandr_output.splitlines():
        if "*" not in line:
            continue
        parts = line.split()
        w_str, _, h_str = parts[0].partition("x")
        if w_str.isdigit() and h_str.isdigit():
            return parts[0]
    return None


def verdict(xrandr_output, configured_mode):
    """(outcome, reason) against the 720p floor and `configured_mode` (an "<w>x<h>" string read
    from the launcher's own --mode argument): "ok" once the current mode clears the floor and
    matches `configured_mode`; "below-floor" if it is below the floor; "mode-mismatch" if it
    clears the floor but differs from `configured_mode`; "error" if xrandr reports no current
    mode at all."""
    mode = current_mode(xrandr_output)
    if mode is None:
        return "error", "xrandr reported no current mode"
    width_str, _, height_str = mode.partition("x")
    width, height = int(width_str), int(height_str)
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return "below-floor", f"{mode} is below the {MIN_WIDTH}x{MIN_HEIGHT} floor"
    if mode != configured_mode:
        return "mode-mismatch", f"xrandr reports {mode}, the launcher configures {configured_mode}"
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
        w_str, _, h_str = parts[0].partition("x")
        if not (w_str.isdigit() and h_str.isdigit()):
            continue
        width, height = int(w_str), int(h_str)
        if "*" in line:
            current = parts[0]
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            below_floor.append((width, height))

    candidate = None
    if below_floor:
        best = max(below_floor, key=lambda mode: mode[0] * mode[1])
        candidate = f"{best[0]}x{best[1]}"
    return connector, current, candidate
