"""The recovery title parser and verdict. Pure: no device, no DOM --
every title, dict and xprop dump is constructed.
"""
from framework.probe import fields as probe_fields, title_lines


def parse_title(title):
    """nonce/unreachable/loading from the probe's own standalone `loading=`
    field (D3: `modules=<faulted>/<loading>`'s unread first half is gone),
    or None if the title carries no WK1 payload, or no `nonce`/
    `unreachable` field."""
    found = probe_fields(title)
    if found is None or "nonce" not in found or "unreachable" not in found:
        return None
    loading_str = found.get("loading", "0")
    loading = int(loading_str) if loading_str.isdigit() else 0
    return {
        "nonce": found["nonce"],
        "unreachable": int(found["unreachable"]),
        "loading": loading,
    }


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
        return "error", "unreachable is still set -- the banner has not cleared"
    if after["loading"] != 0:
        return "error", f"{after['loading']} module(s) are still loading"
    if after["nonce"] != before["nonce"]:
        return "error", (
            f"the page instance changed (nonce {before['nonce']} -> {after['nonce']}) -- "
            "a reload, not a recovery in place")
    return "ok", ""
