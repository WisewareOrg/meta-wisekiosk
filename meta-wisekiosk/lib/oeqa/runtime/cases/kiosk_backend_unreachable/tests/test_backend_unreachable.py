"""Specifies cases/kiosk_backend_unreachable/verdict.py: the probe's own `unreachable=<0|1>
diag=<len> rem=<len>` title-line fields (probe.js: `unreachable` is `[data-backend-unreachable]`'s
presence, `diag`/`rem` are `[data-diagnosis]`/`[data-remediation]`'s own `textContent.length` --
never their text, per the no-leak rule the probe's own header comment states).

Overruled (team-lead): a trivial-looking extractor is still a parser and still gets its own
module, tested -- "case modules carry no parse or branch" (step 1's F6: "parsing and branching
live in the cases module... everything with a branch should live in the package"). This module
does not extend kiosk_applied.verdict's own parse_title/read_sample: that module's `_FIELDS` is
all-or-nothing (every field must be present or the whole title is rejected), and its own fixtures
would need new coverage for fields it doesn't carry today -- a regression risk for marginal reuse.
Independent extraction, the same way kiosk_render and kiosk_applied each have their own verdict.py
despite reading overlapping probe output.

No device, no DOM -- every title and xprop dump is constructed.
"""

from oeqa.runtime.cases.kiosk_backend_unreachable.verdict import parse_title, read_sample, verdict


def test_parse_title_backend_down_with_diagnosis_and_remediation():
    title = "sCgdimfFxt:T | WK1 nonce=1 state=error:configuration cards=-/- faulted=0 unreachable=1 diag=12 rem=20 loading=0"
    assert parse_title(title) == {"unreachable": 1, "diag": 12, "rem": 20}


def test_parse_title_healthy_baseline():
    title = "sCgdimfFxt:T | WK1 nonce=1 state=applied cards=-/- faulted=0 unreachable=0 diag=0 rem=0 loading=0"
    assert parse_title(title) == {"unreachable": 0, "diag": 0, "rem": 0}


def test_parse_title_fields_are_order_independent():
    title = "sCgdimfFxt:T | WK1 rem=20 diag=12 nonce=1 unreachable=1"
    assert parse_title(title) == {"unreachable": 1, "diag": 12, "rem": 20}


def test_parse_title_not_our_probe():
    assert parse_title("sCgdimfFxt:T | WiseKiosk") is None


def test_parse_title_wk1_payload_with_no_unreachable_field():
    # A payload that predates this extension (or simply lacks the field) --
    # distinct from "no probe at all": the marker is present, the field isn't.
    assert parse_title("sCgdimfFxt:T | WK1 nonce=1 state=applied cards=-/- faulted=0") is None


def test_parse_title_empty():
    assert parse_title("") is None


def test_parse_title_skips_a_malformed_token_with_no_equals():
    # A garbage token with no "=" is real, reachable input -- surf's own title
    # wrapping, or stray text past the marker -- not a value the probe itself
    # ever emits maliciously, but still something parse_title must not choke
    # on. kiosk_applied.verdict.parse_title's identical "if sep:" guard is
    # exercised the same way; this module keeps the guard for the same reason.
    title = "sCgdimfFxt:T | WK1 garbage-with-no-equals-sign unreachable=1 diag=12 rem=20"
    assert parse_title(title) == {"unreachable": 1, "diag": 12, "rem": 20}


PAYLOAD = "WK1 nonce=1 state=error:configuration cards=-/- faulted=0 unreachable=1 diag=12 rem=20 loading=0"


def test_read_sample_finds_the_first_probe_payload_among_several_windows():
    xprop_output = (
        'WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n'
        f'WM_NAME(STRING) = "[42%] sCgdimfFxt:T | {PAYLOAD}"\n'
    )
    assert read_sample(xprop_output) == {"unreachable": 1, "diag": 12, "rem": 20}


def test_read_sample_none_when_no_window_carries_a_payload():
    assert read_sample('WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n') is None


def test_read_sample_empty_output_is_none():
    assert read_sample("") is None


def test_read_sample_skips_a_line_with_no_wm_name_property():
    # xprop's real shape for a window with no WM_NAME property at all:
    # "WM_NAME:  not found." -- the same real xprop output
    # kiosk_applied.verdict.read_sample's own test fixture uses, not an
    # invented defect. A real X server has windows like this (window-manager
    # chrome), so the skip is reachable in practice, unlike kiosk_layout's
    # dropped guards against values the probe itself can never emit.
    xprop_output = (
        "WM_NAME:  not found.\n"
        f'WM_NAME(STRING) = "{PAYLOAD}"\n'
    )
    assert read_sample(xprop_output) == {"unreachable": 1, "diag": 12, "rem": 20}


def test_verdict_banner_complete_with_distinct_diagnosis_and_remediation():
    outcome, reason = verdict({"unreachable": 1, "diag": 12, "rem": 20})
    assert outcome == "ok"


def test_verdict_no_probe_payload_is_its_own_error():
    outcome, reason = verdict(None)
    assert outcome == "error"
    assert "no probe payload" in reason.lower() or "none" in reason.lower()


def test_verdict_banner_not_up_is_an_error():
    outcome, reason = verdict({"unreachable": 0, "diag": 12, "rem": 20})
    assert outcome == "error"
    assert "unreachable" in reason.lower() or "banner" in reason.lower()


def test_verdict_empty_diagnosis_is_an_error():
    outcome, reason = verdict({"unreachable": 1, "diag": 0, "rem": 20})
    assert outcome == "error"
    assert "diag" in reason.lower()


def test_verdict_empty_remediation_is_an_error():
    outcome, reason = verdict({"unreachable": 1, "diag": 12, "rem": 0})
    assert outcome == "error"
    assert "rem" in reason.lower()


def test_verdict_diagnosis_and_remediation_the_same_length_is_an_error():
    # The length proxy for "distinct content" -- probe.js can never expose the
    # real text (item 6/the header comment's own no-leak rule), so equal
    # lengths is the one signal available that the two strings might be
    # identical (a copy-paste bug, not a real diagnosis/remediation pair).
    outcome, reason = verdict({"unreachable": 1, "diag": 15, "rem": 15})
    assert outcome == "error"
    assert "length" in reason.lower() or "distinct" in reason.lower() or "same" in reason.lower()
