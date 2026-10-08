"""Extracts the probe's `configuration-error=<0|1>` title-line field.
Pure: no device, no DOM -- every title is a plain Python string.
"""
from framework.probe import fields as probe_fields

_KEY = "configuration-error"


def configuration_error_present(title):
    """Whether the probe's `configuration-error=` field reads `1` in title's
    payload, or None if the title carries no WK1 payload or no
    `configuration-error` field at all."""
    found = probe_fields(title)
    if found is None or _KEY not in found:
        return None
    return found[_KEY] == "1"
