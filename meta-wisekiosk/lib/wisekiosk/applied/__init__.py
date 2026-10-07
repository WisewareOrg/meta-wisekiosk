"""The applied-page title parser and verdict. Pure: no device, no DOM --
every title and sample list is a plain Python value.
"""

_MARKER = "WK1 "
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


def verdict(samples, deadline_passed):
    """The case's outcome over the probe's samples, collected once the
    case's own poll loop has ended -- each sample a parse_title() result,
    or None for a read with no probe payload. "applied" once any sample
    says so; otherwise "failed:<state>" (the last real sample's state),
    "error:no-probe" (every sample was None) or "error:no-window" (no
    sample at all). deadline_passed records whether the loop ended by
    exhausting its budget rather than by an early "applied" sighting -- the
    only case this function does not need to tell apart, since an early
    exit is always an "applied" sighting and is already covered above."""
    real = [sample for sample in samples if sample is not None]

    if any(sample["state"] == "applied" for sample in real):
        return "applied"
    if not samples:
        return "error:no-window"
    if not real:
        return "error:no-probe"
    return f"failed:{real[-1]['state']}"
