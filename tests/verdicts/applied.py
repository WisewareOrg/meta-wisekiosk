"""The on-the-panel observation: parse the probe's window title and judge it. Pure: no device,
no DOM -- every title and sample is a plain Python value.
"""

import re

_MARKER = "WK1 "
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')

_FIELDS = ("nonce", "state", "cards", "origin")

OWN_ORIGINS = ("http://localhost:8080", "http://127.0.0.1:8080")


def _title_lines(xprop_output):
    """Every `WM_NAME(<type>) = "<title>"` line's title, in xprop's document order.

    A line carrying no WM_NAME property (xprop's `WM_NAME:  not found.`) does not match and is
    skipped.

    Args:
        xprop_output (str): xprop's raw per-window dump, one line per window `xwininfo -tree`
            found.

    Returns:
        list[str]: the titles.
    """
    return [m.group(1) for m in (_WM_NAME.match(line) for line in xprop_output.splitlines()) if m]


def _fields(title):
    """The probe's key=value tokens past the `WK1 ` marker.

    A token with no `=` is skipped, never raised on: surf's own title wrapping or stray text
    past the marker is reachable input.

    Args:
        title (str): one window title.

    Returns:
        dict[str, str] | None: the tokens, or None if `title` carries no marker.
    """
    index = title.find(_MARKER)
    if index == -1:
        return None
    found = {}
    for token in title[index + len(_MARKER):].split():
        key, sep, value = token.partition("=")
        if sep:
            found[key] = value
    return found


def parse_title(title):
    """The probe's payload from surf's window title.

    surf renders `[<progress>%] <toggles>:<pagestats> | <title>`, dropping the bracket at 100%.
    surf's own `T <ms> <ms>` paint-timing title carries no marker and parses to None.

    Args:
        title (str): one window title.

    Returns:
        dict[str, str] | None: `_FIELDS`' keys, all strings, or None if the title carries no
            probe payload or lacks any of the fields.
    """
    found = _fields(title)
    if found is None or not all(key in found for key in _FIELDS):
        return None
    return {key: found[key] for key in _FIELDS}


def read_sample(xprop_output):
    """The first window's title that parses to a probe payload.

    Args:
        xprop_output (str): xprop's raw per-window dump.

    Returns:
        dict[str, str] | None: that window's `parse_title` result, or None if no window carries
            a payload.
    """
    for title in _title_lines(xprop_output):
        sample = parse_title(title)
        if sample is not None:
            return sample
    return None


def on_panel(sample):
    """Whether the WiseKiosk instance is on the panel.

    The app applied, served by the board's own backend. The card count is read and recorded,
    never judged.

    Args:
        sample (dict[str, str] | None): a `read_sample` result.

    Returns:
        bool: True iff `sample` is not None, its state is `applied` and its origin is one of
            `OWN_ORIGINS`.
    """
    return sample is not None and sample["state"] == "applied" and sample["origin"] in OWN_ORIGINS
