"""Specifies wisekiosk.applied: parse_title over surf's real window-title shape, and verdict over
a sequence of parsed samples (docs/testing.md section "Running it": the run record's page.<case id>
line and its no-leak guarantee).

surf's own updatetitle() (vendored surf.c, read directly) renders "[<progress>%] <toggles>:
<pagestats> | <title>" while progress != 100, and drops the leading "[NN%] " bracket entirely once
progress reaches 100 -- "<toggles>:<pagestats> | <title>". Both forms are fixtures here, not just
the bracketed one. surf's own built-in paint-timing script (same source) sets
document.title = 'T ' + performance.timing.navigationStart + ' ' + Math.round(performance.now()),
which then gets the same surf-applied wrapping -- the exact "T <ms> <ms>" shape parse_title must
treat as not-probe (tested below), distinct from our own probe's "WK1 " payload.

No device, no DOM -- every title and every sample list is constructed.
"""

import pytest

from wisekiosk.applied import parse_title, verdict

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


# ---------------------------------------------------------------------------- verdict
# samples is the sequence of parse_title results collected over the 90 s window: a dict for a
# found-and-parsed probe sample, None for a sample whose title carried no payload.

def _sample(state):
    return {"nonce": "1", "state": state, "cards": "-/-", "faulted": 0, "unreachable": 0}


@pytest.mark.parametrize(
    ("name", "samples", "deadline_passed", "want"),
    [
        (
            "the first applied sample wins, even before the deadline",
            [_sample("loading"), _sample("applied"), _sample("loading")],
            False,
            "applied",
        ),
        (
            "applied still wins when it is also the sample that reaches the deadline",
            [_sample("loading"), _sample("applied")],
            True,
            "applied",
        ),
        (
            "a deadline with only loading samples fails with that state",
            [_sample("loading"), _sample("loading")],
            True,
            "failed:loading",
        ),
        (
            "a per-sample error:not-app state at the deadline fails with that state",
            [_sample("error:not-app")],
            True,
            "failed:error:not-app",
        ),
        (
            "no payload in any sample is a probe error, not a failure",
            [None, None],
            True,
            "error:no-probe",
        ),
        (
            "a no-payload sample beside a real state does not change the outcome",
            [None, _sample("loading"), None],
            True,
            "failed:loading",
        ),
        (
            "an empty sample list at the deadline is a no-window error",
            [],
            True,
            "error:no-window",
        ),
    ],
)
def test_verdict(name, samples, deadline_passed, want):
    assert verdict(samples, deadline_passed) == want, name
