"""The applied-page title parser and verdict. Pure: no device, no DOM --
every title and sample list is a plain Python value.
"""
import re

_MARKER = "WK1 "
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')
_FIELDS = ("nonce", "state", "cards", "faulted", "unreachable")
_INT_FIELDS = ("faulted", "unreachable")


def parse_title(title):
    """The probe's payload from surf's window title ("[<progress>%]
    <toggles>:<pagestats> | <title>", or with the bracket dropped once
    progress reaches 100), or None if the title carries no WK1 payload --
    including surf's own "T <ms> <ms>" paint-timing title."""
    index = title.find(_MARKER)
    if index == -1:
        return None
    fields = {}
    for token in title[index + len(_MARKER):].split():
        key, sep, value = token.partition("=")
        if sep:
            fields[key] = value
    if not all(key in fields for key in _FIELDS):
        return None
    return {key: (int(fields[key]) if key in _INT_FIELDS else fields[key]) for key in _FIELDS}


def read_sample(xprop_output):
    """The applied-page sample from xprop's raw per-window dump (one
    WM_NAME(<type>) = "<title>" line per window xwininfo -tree found) --
    the first window whose title parses to a probe payload, or None if no
    window carries one."""
    for line in xprop_output.splitlines():
        m = _WM_NAME.match(line)
        if not m:
            continue
        sample = parse_title(m.group(1))
        if sample is not None:
            return sample
    return None


def verdict(samples):
    """The case's outcome over the probe's samples, collected once the
    case's own poll loop has ended -- each sample a parse_title() result,
    or None for a read with no probe payload. "applied" once any sample
    says so; otherwise "failed:<state>" (the last real sample's state), or
    "error:no-probe" (every sample was None)."""
    real = [sample for sample in samples if sample is not None]

    if any(sample["state"] == "applied" for sample in real):
        return "applied"
    if not real:
        return "error:no-probe"
    return f"failed:{real[-1]['state']}"
