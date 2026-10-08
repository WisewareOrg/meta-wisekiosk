"""Specifies cases/kiosk_config_errors/verdict.py: the probe's own
`configuration-error=<0|1>` title-line field -- the frontend decides whether a fault is shown
(design's selection rule: config-validation detail is the app's own tier, not re-verified here);
this module only reads the field's own boolean back, the same way kiosk_applied/verdict.py's
parse_title reads its own fields.

No device, no DOM -- every title is a constructed string.
"""

import pytest

from oeqa.runtime.cases.kiosk_config_errors.verdict import configuration_error_present


@pytest.mark.parametrize(
    ("name", "title", "want"),
    [
        ("a fault is shown", "sCgdimfFxt:T | WK1 configuration-error=1", True),
        ("no fault is shown", "sCgdimfFxt:T | WK1 configuration-error=0", False),
        (
            "no configuration-error field at all -- a payload predating the field",
            "sCgdimfFxt:T | WK1 nonce=1 state=applied cards=-/- faulted=0 unreachable=0",
            None,
        ),
        (
            "the field among other unrelated fields, order independent",
            "sCgdimfFxt:T | WK1 nonce=1 configuration-error=1 state=error:configuration",
            True,
        ),
        ("empty title carries no field", "", None),
    ],
)
def test_configuration_error_present(name, title, want):
    assert configuration_error_present(title) == want, name
