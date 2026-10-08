"""Specifies cases/kiosk_config_errors/verdict.py: the probe's own
`configuration-error=<state>` title-line field, extracted and nothing more --
the frontend decides absent/unparsable/rejected (design's selection rule:
config-validation detail is the app's own tier, not re-verified here); this
module only reads the field back out, the same way kiosk_applied/verdict.py's
parse_title reads its own fields.

No device, no DOM -- every title is a constructed string.
"""

import pytest

from oeqa.runtime.cases.kiosk_config_errors.verdict import parse_configuration_error


@pytest.mark.parametrize(
    ("name", "title", "want"),
    [
        ("absent state", "sCgdimfFxt:T | WK1 configuration-error=absent", "absent"),
        ("unparsable state", "sCgdimfFxt:T | WK1 configuration-error=unparsable", "unparsable"),
        ("rejected state", "sCgdimfFxt:T | WK1 configuration-error=rejected", "rejected"),
        (
            "no configuration-error field at all -- the healthy baseline title",
            "sCgdimfFxt:T | WK1 nonce=1 state=applied cards=-/- faulted=0 unreachable=0",
            None,
        ),
        (
            "the field among other unrelated fields, order independent",
            "sCgdimfFxt:T | WK1 nonce=1 configuration-error=rejected state=applied",
            "rejected",
        ),
        ("empty title carries no field", "", None),
        (
            # A pure extractor does not validate -- it passes through whatever
            # string follows the key, the same way parse_title never checks
            # that `state=` is one of a known set. Judgement call, flagged to
            # tree-impl: whoever asserts against the SEEDED state is where an
            # unrecognised value would actually matter.
            "an unrecognised value is still extracted verbatim, not collapsed to None",
            "sCgdimfFxt:T | WK1 configuration-error=some-future-state",
            "some-future-state",
        ),
    ],
)
def test_parse_configuration_error(name, title, want):
    assert parse_configuration_error(title) == want, name
