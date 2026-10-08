"""The applied-page title parser and verdict. Pure: no device, no DOM --
every title and sample list is a plain Python value.
"""
from framework.probe import fields as probe_fields, title_lines

_FIELDS = ("nonce", "state", "cards", "faulted", "unreachable")
_INT_FIELDS = ("faulted", "unreachable")


def parse_title(title):
    """The probe's payload from surf's window title ("[<progress>%]
    <toggles>:<pagestats> | <title>", or with the bracket dropped once
    progress reaches 100), or None if the title carries no WK1 payload --
    including surf's own "T <ms> <ms>" paint-timing title -- or is missing
    any of the five fields this case's own contract requires."""
    found = probe_fields(title)
    if found is None or not all(key in found for key in _FIELDS):
        return None
    return {key: (int(found[key]) if key in _INT_FIELDS else found[key]) for key in _FIELDS}


def read_sample(xprop_output):
    """The applied-page sample from xprop's raw per-window dump (one
    WM_NAME(<type>) = "<title>" line per window xwininfo -tree found) --
    the first window whose title parses to a probe payload, or None if no
    window carries one."""
    for title in title_lines(xprop_output):
        sample = parse_title(title)
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
