"""The layout-floor title parser and verdict. Pure: no device, no DOM --
every title and parsed dict is a plain Python value.
"""

_MARKER = "WK1 "

_MIN_WIDTH = 1280
_MIN_HEIGHT = 720


def parse_layout(title):
    """The probe's `layout=<w>x<h>:<clear|overlap:<id>>` field, or None if
    the title carries no layout payload."""
    index = title.find(_MARKER)
    if index == -1:
        return None
    value = None
    for token in title[index + len(_MARKER):].split():
        key, sep, val = token.partition("=")
        if sep and key == "layout":
            value = val
            break
    if value is None:
        return None
    dims, _, rest = value.partition(":")
    w_str, _, h_str = dims.partition("x")
    width, height = int(w_str), int(h_str)
    if rest.startswith("overlap:"):
        return {"width": width, "height": height, "clear": False,
                 "overlap_id": rest[len("overlap:"):]}
    return {"width": width, "height": height, "clear": True, "overlap_id": None}


def verdict(parsed):
    """("ok"|"error", reason) against the 720p floor and band clearance."""
    if parsed["width"] < _MIN_WIDTH:
        return "error", f"width {parsed['width']} is below the {_MIN_WIDTH} floor"
    if parsed["height"] < _MIN_HEIGHT:
        return "error", f"height {parsed['height']} is below the {_MIN_HEIGHT} floor"
    if not parsed["clear"]:
        return "error", f"region {parsed['overlap_id']} overlaps the band"
    return "ok", ""
