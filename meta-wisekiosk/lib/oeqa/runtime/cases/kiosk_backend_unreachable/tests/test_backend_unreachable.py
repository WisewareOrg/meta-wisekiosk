"""Specifies cases/kiosk_backend_unreachable/verdict.py: the probe's own `unreachable=<0|1>`
title-line field (probe.js: `unreachable` is `[data-backend-unreachable]`'s own presence).

No device, no DOM -- every title and xprop dump is constructed.
"""

from oeqa.runtime.cases.kiosk_backend_unreachable.verdict import parse_title, read_sample, verdict


def test_parse_title_backend_down():
    title = "sCgdimfFxt:T | WK1 nonce=1 state=error:configuration cards=-/- faulted=0 unreachable=1"
    assert parse_title(title) == {"unreachable": 1}


def test_parse_title_healthy_baseline():
    title = "sCgdimfFxt:T | WK1 nonce=1 state=applied cards=-/- faulted=0 unreachable=0"
    assert parse_title(title) == {"unreachable": 0}


def test_parse_title_fields_are_order_independent():
    title = "sCgdimfFxt:T | WK1 nonce=1 unreachable=1"
    assert parse_title(title) == {"unreachable": 1}


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
    title = "sCgdimfFxt:T | WK1 garbage-with-no-equals-sign unreachable=1"
    assert parse_title(title) == {"unreachable": 1}


PAYLOAD = "WK1 nonce=1 state=error:configuration cards=-/- faulted=0 unreachable=1"


def test_read_sample_finds_the_first_probe_payload_among_several_windows():
    xprop_output = (
        'WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n'
        f'WM_NAME(STRING) = "[42%] sCgdimfFxt:T | {PAYLOAD}"\n'
    )
    assert read_sample(xprop_output) == {"unreachable": 1}


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
    assert read_sample(xprop_output) == {"unreachable": 1}


def test_verdict_signal_up():
    outcome, reason = verdict({"unreachable": 1})
    assert outcome == "ok"


def test_verdict_no_probe_payload_is_its_own_error():
    outcome, reason = verdict(None)
    assert outcome == "error"
    assert "no probe payload" in reason.lower() or "none" in reason.lower()


def test_verdict_signal_not_up_is_an_error():
    outcome, reason = verdict({"unreachable": 0})
    assert outcome == "error"
    assert "unreachable" in reason.lower() or "signal" in reason.lower()
