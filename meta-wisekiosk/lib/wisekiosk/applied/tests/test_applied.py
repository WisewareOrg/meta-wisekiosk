"""Specifies wisekiosk.applied: parse_title over surf's window-title shape, and verdict over a
sequence of parsed samples (docs/testing.md section "Running it": the run record's page.<case id>
line and its no-leak guarantee).

surf's updatetitle() (vendored surf.c) renders "[<progress>%] <toggles>:<pagestats> | <title>"
while progress != 100, and drops the leading "[NN%] " bracket once progress reaches 100 --
"<toggles>:<pagestats> | <title>"; both forms are fixtures here. surf's own built-in paint-timing
script sets document.title = 'T ' + performance.timing.navigationStart + ' ' +
Math.round(performance.now()), wrapped the same way -- the "T <ms> <ms>" shape parse_title must
treat as not-probe, distinct from our probe's "WK1 " payload.

No device, no DOM -- every title and every sample list is constructed.
"""

import pytest

from wisekiosk.applied import parse_title, read_sample, verdict

PROBE = "WK1 nonce=1699999999.5 state=applied cards=-/- faulted=0 unreachable=0"


@pytest.mark.parametrize(
    ("name", "title", "want"),
    [
        (
            "progress-bracketed form (surf.c: '[%i%%] %s:%s | %s')",
            f"[42%] sCgdimfFxt:T | {PROBE}",
            {"nonce": "1699999999.5", "state": "applied", "cards": "-/-", "faulted": 0,
             "unreachable": 0},
        ),
        (
            "progress==100 drops the bracket entirely (surf.c: '%s:%s | %s')",
            f"sCgdimfFxt:T | {PROBE}",
            {"nonce": "1699999999.5", "state": "applied", "cards": "-/-", "faulted": 0,
             "unreachable": 0},
        ),
        (
            "a colon-bearing state value is not truncated at the colon",
            "[7%] sCgdimfFxt:T | WK1 nonce=42 state=error:not-app cards=-/- faulted=0 unreachable=0",
            {"nonce": "42", "state": "error:not-app", "cards": "-/-", "faulted": 0, "unreachable": 0},
        ),
        (
            "faulted and unreachable carry their real, nonzero values",
            "sCgdimfFxt:T | WK1 nonce=1 state=loading cards=-/- faulted=3 unreachable=1",
            {"nonce": "1", "state": "loading", "cards": "-/-", "faulted": 3, "unreachable": 1},
        ),
    ],
)
def test_parse_title_finds_the_payload(name, title, want):
    assert parse_title(title) == want, name


@pytest.mark.parametrize(
    ("name", "title"),
    [
        ("surf's own 'T <ms> <ms>' timing payload is not our probe, wrapped as surf renders it",
         "sCgdimfFxt:T | T 1763000000000 842"),
        ("surf's own timing payload, unwrapped", "T 1763000000000 842"),
        ("a plain page title carrying no payload at all", "sCgdimfFxt:T | WiseKiosk"),
        ("the WK1 marker present but the payload past it is not key=value pairs",
         "sCgdimfFxt:T | WK1 not-a-valid-payload-at-all"),
        ("empty title", ""),
    ],
)
def test_parse_title_returns_none_for_not_probe(name, title):
    assert parse_title(title) is None, name


# ------------------------------------------------------------------------- read_sample
# F6: moves the case's own per-window scan out of kiosk.py. Input is xprop's raw,
# unindented output for every window xwininfo -tree found ("WM_NAME(STRING) =
# "<title>"" per window, one per line); returns the first window's parsed sample
# that is not None, or None if no window carries one.

def test_read_sample_finds_the_first_probe_payload_among_several_windows():
    xprop_output = (
        'WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n'
        f'WM_NAME(STRING) = "[42%] sCgdimfFxt:T | {PROBE}"\n'
    )
    assert read_sample(xprop_output) == {
        "nonce": "1699999999.5", "state": "applied", "cards": "-/-", "faulted": 0,
        "unreachable": 0,
    }


def test_read_sample_none_when_no_window_carries_a_payload():
    xprop_output = 'WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n'
    assert read_sample(xprop_output) is None


def test_read_sample_empty_output_is_none():
    assert read_sample("") is None


def test_read_sample_skips_a_line_with_no_wm_name_property():
    # xprop's real shape for a window with no WM_NAME property at all:
    # "WM_NAME:  not found." -- a different shape from the matching line, which
    # the scan must skip rather than stop on.
    xprop_output = (
        "WM_NAME:  not found.\n"
        f'WM_NAME(STRING) = "{PROBE}"\n'
    )
    assert read_sample(xprop_output) == {
        "nonce": "1699999999.5", "state": "applied", "cards": "-/-", "faulted": 0,
        "unreachable": 0,
    }


# ---------------------------------------------------------------------------- verdict
# samples is the sequence of parse_title results collected over the 90 s window: a dict for a
# found-and-parsed probe sample, None for a sample whose title carried no payload. The case's own
# poll loop always appends at least one sample before calling verdict, so an empty list is
# unreachable from production and is not a case here (D2).

def _sample(state):
    return {"nonce": "1", "state": state, "cards": "-/-", "faulted": 0, "unreachable": 0}


@pytest.mark.parametrize(
    ("name", "samples", "want"),
    [
        (
            "the first applied sample wins",
            [_sample("loading"), _sample("applied"), _sample("loading")],
            "applied",
        ),
        (
            "a deadline with only loading samples fails with that state",
            [_sample("loading"), _sample("loading")],
            "failed:loading",
        ),
        (
            "a per-sample error:not-app state at the deadline fails with that state",
            [_sample("error:not-app")],
            "failed:error:not-app",
        ),
        (
            "no payload in any sample is a probe error, not a failure",
            [None, None],
            "error:no-probe",
        ),
        (
            "a no-payload sample beside a real state does not change the outcome",
            [None, _sample("loading"), None],
            "failed:loading",
        ),
    ],
)
def test_verdict(name, samples, want):
    assert verdict(samples) == want, name
