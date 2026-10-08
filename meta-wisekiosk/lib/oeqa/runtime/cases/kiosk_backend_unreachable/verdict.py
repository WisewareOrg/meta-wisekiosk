"""The backend-unreachable title parser and verdict. Pure: no device, no
DOM -- every title and sample is a plain Python value.
"""
from framework.probe import fields as probe_fields, title_lines


def parse_title(title):
    """unreachable/diag/rem from the probe's payload, or None if the title
    carries no WK1 payload or no `unreachable` field."""
    found = probe_fields(title)
    if found is None or "unreachable" not in found:
        return None
    return {
        "unreachable": int(found["unreachable"]),
        "diag": int(found.get("diag", "0")),
        "rem": int(found.get("rem", "0")),
    }


def read_sample(xprop_output):
    """The backend-unreachable sample from xprop's raw per-window dump --
    the first window whose title parses to a probe payload, or None."""
    for title in title_lines(xprop_output):
        sample = parse_title(title)
        if sample is not None:
            return sample
    return None


def verdict(parsed):
    """("ok"|"error", reason) for the backend-unreachable banner."""
    if parsed is None:
        return "error", "no probe payload"
    if parsed["unreachable"] != 1:
        return "error", "unreachable is not set -- the banner is not up"
    if parsed["diag"] == 0:
        return "error", "diag is empty"
    if parsed["rem"] == 0:
        return "error", "rem is empty"
    if parsed["diag"] == parsed["rem"]:
        return "error", "diag and rem are the same length -- not distinct content"
    return "ok", ""
