"""The backend-unreachable title parser and verdict. Pure: no device, no
DOM -- every title and sample is a plain Python value.
"""
import re

_MARKER = "WK1 "
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')


def parse_title(title):
    """unreachable/diag/rem from the probe's payload, or None if the title
    carries no WK1 payload or no `unreachable` field."""
    index = title.find(_MARKER)
    if index == -1:
        return None
    fields = {}
    for token in title[index + len(_MARKER):].split():
        key, sep, value = token.partition("=")
        if sep:
            fields[key] = value
    if "unreachable" not in fields:
        return None
    return {
        "unreachable": int(fields["unreachable"]),
        "diag": int(fields.get("diag", "0")),
        "rem": int(fields.get("rem", "0")),
    }


def read_sample(xprop_output):
    """The backend-unreachable sample from xprop's raw per-window dump --
    the first window whose title parses to a probe payload, or None."""
    for line in xprop_output.splitlines():
        m = _WM_NAME.match(line)
        if not m:
            continue
        sample = parse_title(m.group(1))
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
