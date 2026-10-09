"""The applied-page title parser and verdict. Pure: no device, no DOM --
every title and sample list is a plain Python value.
"""
import re

_MARKER = "WK1 "
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')

_FIELDS = ("nonce", "state", "cards", "faulted", "unreachable")
_INT_FIELDS = ("faulted", "unreachable")
_CARDS_PAIR = re.compile(r'^(\d+)/(\d+)$')


def _cards_value(value):
    """value as a (present, live) int pair if it matches "<present>/<live>",
    else value unchanged -- the no-count placeholder "-/-" (no replay set
    active, or a declared transport failure) passes through as the raw
    string."""
    m = _CARDS_PAIR.match(value)
    return (int(m.group(1)), int(m.group(2))) if m else value


def _title_lines(xprop_output):
    """Every WM_NAME(<type>) = "<title>" line's <title>, in xprop's own
    document order -- xprop's raw per-window dump, one line per window
    xwininfo -tree found. A line carrying no WM_NAME property (xprop's own
    "WM_NAME:  not found.") does not match and is skipped."""
    return [m.group(1) for m in (_WM_NAME.match(line) for line in xprop_output.splitlines()) if m]


def _fields(title):
    """The probe's key=value tokens past _MARKER, as a dict, or None if
    title carries no WK1 payload at all. A token with no "=" is skipped,
    never raised on -- real, reachable input (surf's own title wrapping,
    or stray text past the marker), not a value the probe itself emits."""
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
    """The probe's payload from surf's window title ("[<progress>%]
    <toggles>:<pagestats> | <title>", or with the bracket dropped once
    progress reaches 100), or None if the title carries no WK1 payload --
    including surf's own "T <ms> <ms>" paint-timing title -- or is missing
    any of the five fields this case's own contract requires."""
    found = _fields(title)
    if found is None or not all(key in found for key in _FIELDS):
        return None
    result = {}
    for key in _FIELDS:
        if key in _INT_FIELDS:
            result[key] = int(found[key])
        elif key == "cards":
            result[key] = _cards_value(found[key])
        else:
            result[key] = found[key]
    return result


def read_sample(xprop_output):
    """The applied-page sample from xprop's raw per-window dump (one
    WM_NAME(<type>) = "<title>" line per window xwininfo -tree found) --
    the first window whose title parses to a probe payload, or None if no
    window carries one."""
    for title in _title_lines(xprop_output):
        sample = parse_title(title)
        if sample is not None:
            return sample
    return None


def verdict(samples):
    """The case's outcome over the probe's samples, collected once the
    case's own poll loop has ended -- each sample a parse_title() result,
    or None for a read with no probe payload: ("applied", "") once any
    sample says so; ("failed", <state>) for the last real sample's own
    state; ("error", "no-probe") if every sample was None."""
    real = [sample for sample in samples if sample is not None]

    if any(sample["state"] == "applied" for sample in real):
        return "applied", ""
    if not real:
        return "error", "no-probe"
    return "failed", real[-1]["state"]
