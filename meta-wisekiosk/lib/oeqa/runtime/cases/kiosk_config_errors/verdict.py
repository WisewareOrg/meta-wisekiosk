"""Extracts the probe's `configuration-error=<state>` title-line field.
Pure: no device, no DOM -- every title is a plain Python string.
"""
from framework.probe import fields as probe_fields

_KEY = "configuration-error"


def parse_configuration_error(title):
    """The value following `configuration-error=` in the probe's payload, or
    None if the field is absent. A pure extractor: whatever string follows
    the key is returned verbatim, never validated against a known set."""
    found = probe_fields(title)
    if found is None:
        return None
    return found.get(_KEY)
