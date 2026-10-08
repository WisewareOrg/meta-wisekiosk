"""The recovery title parser and verdict. Pure: no device, no DOM --
every title, dict and xprop dump is constructed.
"""
from framework.probe import fields as probe_fields, title_lines


def parse_title(title):
    """nonce/unreachable from the probe's payload, or None if the title
    carries no WK1 payload, or no `nonce`/`unreachable` field."""
    found = probe_fields(title)
    if found is None or "nonce" not in found or "unreachable" not in found:
        return None
    return {"nonce": found["nonce"], "unreachable": int(found["unreachable"])}


def read_sample(xprop_output):
    """The recovery sample from xprop's raw per-window dump -- the first
    window whose title parses to a probe payload, or None."""
    for title in title_lines(xprop_output):
        sample = parse_title(title)
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
        return "error", "unreachable is still set -- the degraded signal has not cleared"
    if after["nonce"] != before["nonce"]:
        return "error", (
            f"the page instance changed (nonce {before['nonce']} -> {after['nonce']}) -- "
            "a reload, not a recovery in place")
    return "ok", ""
