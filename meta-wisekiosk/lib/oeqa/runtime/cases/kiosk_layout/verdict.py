"""Specifies cases/kiosk_layout/verdict.py: the probe's own `layout=<w>x<h>:<clear|overlap:<id>>
edge=<clear|unknown|<id>>` title-line fields, parsed and judged against the 720p floor, band
clearance and the configured edge margin (the ticket's "Decided": the display's designed layout
renders correctly at 720p or better, asserted at whatever mode xrandr reports).

Pure: no device, no DOM -- every title, parsed dict and xrandr dump is a plain Python value.
"""
from framework.probe import fields as probe_fields

_MIN_WIDTH = 1280
_MIN_HEIGHT = 720


def parse_layout(title):
    """The probe's `layout=`/`edge=` fields, or None if the title carries
    no layout payload at all. `edge` defaults to "unknown" when the title
    carries a layout= field but no edge= one (a title predating the F3
    extension) -- never silently treated as clear."""
    found = probe_fields(title)
    if found is None or "layout" not in found:
        return None
    value = found["layout"]
    dims, _, rest = value.partition(":")
    w_str, _, h_str = dims.partition("x")
    width, height = int(w_str), int(h_str)
    if rest.startswith("overlap:"):
        clear, overlap_id = False, rest[len("overlap:"):]
    else:
        clear, overlap_id = True, None
    return {
        "width": width, "height": height, "clear": clear, "overlap_id": overlap_id,
        "edge": found.get("edge", "unknown"),
    }


def verdict(parsed):
    """("ok"|"error", reason) against the 720p floor, band clearance and
    edge margin. "unknown" (config.json was not fetchable from the probe)
    is never a silent pass (round-1 review F3)."""
    if parsed["width"] < _MIN_WIDTH:
        return "error", f"width {parsed['width']} is below the {_MIN_WIDTH} floor"
    if parsed["height"] < _MIN_HEIGHT:
        return "error", f"height {parsed['height']} is below the {_MIN_HEIGHT} floor"
    if not parsed["clear"]:
        return "error", f"region {parsed['overlap_id']} overlaps the band"
    if parsed["edge"] == "unknown":
        return "error", "edge margin could not be confirmed -- config.json was not fetchable from the probe"
    if parsed["edge"] != "clear":
        return "error", f"{parsed['edge']} comes within the configured edge band of a viewport edge"
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
