"""The recovery title parser and verdict. Pure: no device, no DOM --
every title and sample is a plain Python value.
"""
import re

_MARKER = "WK1 "
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')


def parse_title(title):
    """nonce/unreachable/loading from the probe's payload, or None if the
    title carries no WK1 payload, or no `nonce`/`unreachable` field."""
    index = title.find(_MARKER)
    if index == -1:
        return None
    fields = {}
    for token in title[index + len(_MARKER):].split():
        key, sep, value = token.partition("=")
        if sep:
            fields[key] = value
    if "nonce" not in fields or "unreachable" not in fields:
        return None
    loading = 0
    if "modules" in fields:
        _unavailable, _sep, loading_str = fields["modules"].partition("/")
        loading = int(loading_str) if loading_str.isdigit() else 0
    return {
        "nonce": fields["nonce"],
        "unreachable": int(fields["unreachable"]),
        "loading": loading,
    }


def read_sample(xprop_output):
    """The recovery sample from xprop's raw per-window dump -- the first
    window whose title parses to a probe payload, or None."""
    for line in xprop_output.splitlines():
        m = _WM_NAME.match(line)
        if not m:
            continue
        sample = parse_title(m.group(1))
        if sample is not None:
            return sample
    return None


def verdict(before, after):
    """("ok"|"error", reason) comparing the sample taken before starting
    the backend against the sample taken after."""
    if before is None:
        return "error", "no probe payload before starting the backend"
    if after is None:
        return "error", "no probe payload after starting the backend"
    if after["unreachable"] != 0:
        return "error", "unreachable is still set -- the banner has not cleared"
    if after["loading"] != 0:
        return "error", f"{after['loading']} module(s) are still loading"
    if after["nonce"] != before["nonce"]:
        return "error", (
            f"the page instance changed (nonce {before['nonce']} -> {after['nonce']}) -- "
            "a reload, not a recovery in place")
    return "ok", ""
