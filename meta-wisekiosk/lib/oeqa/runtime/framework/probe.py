"""Window-title probe primitives shared by every case that reads the DOM
probe through surf's window title (docs/testing.md § "The render and
applied cases"). Pure: no device, no DOM -- every argument and result is a
plain string, list or dict.
"""
import re

MARKER = "WK1 "
WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')


def title_lines(xprop_output):
    """Every WM_NAME(<type>) = "<title>" line's <title>, in xprop's own
    document order -- xprop's raw per-window dump, one line per window
    xwininfo -tree found. A line carrying no WM_NAME property (xprop's own
    "WM_NAME:  not found.") does not match and is skipped."""
    return [m.group(1) for m in (WM_NAME.match(line) for line in xprop_output.splitlines()) if m]


def fields(title):
    """The probe's key=value tokens past MARKER, as a dict, or None if
    title carries no WK1 payload at all. A token with no "=" is skipped,
    never raised on -- real, reachable input (surf's own title wrapping,
    or stray text past the marker), not a value the probe itself emits."""
    index = title.find(MARKER)
    if index == -1:
        return None
    found = {}
    for token in title[index + len(MARKER):].split():
        key, sep, value = token.partition("=")
        if sep:
            found[key] = value
    return found
