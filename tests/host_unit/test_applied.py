"""Specifies tests/verdicts/applied.py: parse_title over surf's window-title shapes, read_sample
over xprop's per-window dump, and on_panel over constructed samples.

surf's updatetitle() renders "[<progress>%] <toggles>:<pagestats> | <title>" while progress is
not 100 and drops the leading "[NN%] " bracket at 100. surf's own paint-timing script sets
document.title to 'T <ms> <ms>', wrapped the same way -- not a probe payload.

No device, no DOM -- every title and sample is constructed.
"""

import pytest

from verdicts.applied import OWN_ORIGINS, on_panel, parse_title, read_sample

PROBE = "WK1 nonce=1699999999.5 state=applied cards=4/4 origin=http://localhost:8080"
SAMPLE = {"nonce": "1699999999.5", "state": "applied", "cards": "4/4",
          "origin": "http://localhost:8080"}


@pytest.mark.parametrize(
    ("name", "title"),
    [
        ("progress-bracketed form", f"[42%] sCgdimfFxt:T | {PROBE}"),
        ("progress==100 drops the bracket", f"sCgdimfFxt:T | {PROBE}"),
        ("unwrapped", PROBE),
    ],
)
def test_parse_title_finds_the_payload(name, title):
    assert parse_title(title) == SAMPLE, name


def test_parse_title_keeps_a_colon_bearing_state_whole():
    title = "[7%] sCgdimfFxt:T | WK1 nonce=42 state=error:not-app cards=0/0 origin=null"
    assert parse_title(title) == {"nonce": "42", "state": "error:not-app", "cards": "0/0",
                                  "origin": "null"}


@pytest.mark.parametrize(
    ("name", "title"),
    [
        ("surf's own timing title, wrapped", "sCgdimfFxt:T | T 1763000000000 842"),
        ("title with no marker", "sCgdimfFxt:T | WiseKiosk"),
        ("marker with no key=value pairs", "sCgdimfFxt:T | WK1 not-a-payload"),
        ("payload missing a field", "WK1 nonce=1 state=applied cards=0/0"),
        ("empty title", ""),
    ],
)
def test_parse_title_returns_none_for_not_a_payload(name, title):
    assert parse_title(title) is None, name


def test_read_sample_first_parsing_window_wins():
    other = PROBE.replace("nonce=1699999999.5", "nonce=2")
    xprop_output = (
        'WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n'
        f'WM_NAME(STRING) = "[42%] sCgdimfFxt:T | {PROBE}"\n'
        f'WM_NAME(STRING) = "{other}"\n'
    )
    assert read_sample(xprop_output) == SAMPLE


def test_read_sample_skips_a_window_with_no_wm_name():
    xprop_output = f"WM_NAME:  not found.\nWM_NAME(STRING) = \"{PROBE}\"\n"
    assert read_sample(xprop_output) == SAMPLE


@pytest.mark.parametrize("xprop_output", ["", 'WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n'])
def test_read_sample_none_when_no_window_carries_a_payload(xprop_output):
    assert read_sample(xprop_output) is None


def _sample(state="applied", origin="http://localhost:8080"):
    """A read_sample-shaped sample with the given state and origin."""
    return {"nonce": "1", "state": state, "cards": "0/0", "origin": origin}


@pytest.mark.parametrize("origin", OWN_ORIGINS)
def test_on_panel_true_for_applied_from_each_own_origin(origin):
    assert on_panel(_sample(origin=origin))


@pytest.mark.parametrize(
    ("name", "sample"),
    [
        ("no sample", None),
        ("loading", _sample("loading")),
        ("not the app", _sample("error:not-app")),
        ("configuration error", _sample("error:configuration")),
        ("applied from a foreign origin", _sample(origin="http://example.invalid")),
    ],
)
def test_on_panel_false(name, sample):
    assert not on_panel(sample), name
