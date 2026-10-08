"""Extracts the probe's `configuration-error=<state>` title-line field.
Pure: no device, no DOM -- every title is a plain Python string.
"""

_MARKER = "WK1 "
_KEY = "configuration-error"


def parse_configuration_error(title):
    """The value following `configuration-error=` in the probe's payload, or
    None if the field is absent. A pure extractor: whatever string follows
    the key is returned verbatim, never validated against a known set."""
    index = title.find(_MARKER)
    if index == -1:
        return None
    for token in title[index + len(_MARKER):].split():
        key, sep, value = token.partition("=")
        if sep and key == _KEY:
            return value
    return None
