"""Specifies cases/kiosk_recovery/verdict.py: the probe's own `nonce=<...> unreachable=<0|1>
loading=<n>` title-line fields, read before and after starting the backend -- recovery is "the
banner is gone, every stood-down module has resolved (loading == 0), and it is the same page
instance (nonce unchanged)," never a reload.

D3 (round-1 review): the probe's own `loading=<n>` field is standalone -- `modules=<faulted>/
<loading>`'s unread first half (`faulted`, already reported on its own) is gone.

Overruled (team-lead): "case modules carry no parse or branch" (step 1's F6) applies here as much
as to kiosk_backend_unreachable -- independent extraction, same reasoning, not an extension of
kiosk_applied.verdict's all-or-nothing parse_title.

No device, no DOM -- every title, dict and xprop dump is constructed.
"""

from oeqa.runtime.cases.kiosk_recovery.verdict import parse_title, read_sample, verdict


def test_parse_title_backend_down_before_recovery():
    title = "sCgdimfFxt:T | WK1 nonce=100 state=error:configuration cards=-/- faulted=0 unreachable=1 loading=3"
    assert parse_title(title) == {"nonce": "100", "unreachable": 1, "loading": 3}


def test_parse_title_recovered():
    title = "sCgdimfFxt:T | WK1 nonce=100 state=applied cards=-/- faulted=0 unreachable=0 loading=0"
    assert parse_title(title) == {"nonce": "100", "unreachable": 0, "loading": 0}


def test_parse_title_some_modules_still_loading():
    title = "sCgdimfFxt:T | WK1 nonce=100 state=applied cards=-/- faulted=0 unreachable=0 loading=2"
    assert parse_title(title) == {"nonce": "100", "unreachable": 0, "loading": 2}


def test_parse_title_fields_are_order_independent():
    title = "sCgdimfFxt:T | WK1 loading=2 unreachable=0 nonce=100"
    assert parse_title(title) == {"nonce": "100", "unreachable": 0, "loading": 2}


def test_parse_title_no_loading_field_defaults_to_zero():
    # A title predating the loading= extension still parses -- loading is
    # simply unknown, treated as zero (nothing reported as still loading),
    # never a crash.
    title = "sCgdimfFxt:T | WK1 nonce=100 unreachable=0"
    assert parse_title(title) == {"nonce": "100", "unreachable": 0, "loading": 0}


def test_parse_title_not_our_probe():
    assert parse_title("sCgdimfFxt:T | WiseKiosk") is None


def test_parse_title_wk1_payload_missing_unreachable_or_nonce():
    assert parse_title("sCgdimfFxt:T | WK1 state=applied cards=-/- faulted=0") is None


def test_parse_title_empty():
    assert parse_title("") is None


def test_parse_title_skips_a_malformed_token_with_no_equals():
    # Real, reachable input (surf's own title wrapping or stray text past
    # the marker), not a value the probe itself emits maliciously -- the same
    # "if sep:" guard kiosk_applied.verdict.parse_title already keeps and
    # tests, kept here for the same reason.
    title = "sCgdimfFxt:T | WK1 garbage-with-no-equals-sign nonce=100 unreachable=0 loading=0"
    assert parse_title(title) == {"nonce": "100", "unreachable": 0, "loading": 0}


BEFORE_PAYLOAD = "WK1 nonce=100 state=error:configuration cards=-/- faulted=0 unreachable=1 loading=3"


def test_read_sample_finds_the_first_probe_payload_among_several_windows():
    xprop_output = (
        'WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n'
        f'WM_NAME(STRING) = "[42%] sCgdimfFxt:T | {BEFORE_PAYLOAD}"\n'
    )
    assert read_sample(xprop_output) == {"nonce": "100", "unreachable": 1, "loading": 3}


def test_read_sample_none_when_no_window_carries_a_payload():
    assert read_sample('WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n') is None


def test_read_sample_empty_output_is_none():
    assert read_sample("") is None


def test_read_sample_skips_a_line_with_no_wm_name_property():
    # xprop's real shape for a window with no WM_NAME property -- the same
    # real fixture kiosk_applied.verdict.read_sample's own test uses. A real
    # X server has windows like this, so the skip is reachable in practice,
    # unlike kiosk_layout's dropped guards against probe-emitted values.
    xprop_output = (
        "WM_NAME:  not found.\n"
        f'WM_NAME(STRING) = "{BEFORE_PAYLOAD}"\n'
    )
    assert read_sample(xprop_output) == {"nonce": "100", "unreachable": 1, "loading": 3}


def test_verdict_recovered_same_instance():
    outcome, reason = verdict(
        before={"nonce": "100", "unreachable": 1, "loading": 3},
        after={"nonce": "100", "unreachable": 0, "loading": 0},
    )
    assert outcome == "ok"


def test_verdict_no_before_sample_is_an_error():
    outcome, reason = verdict(before=None, after={"nonce": "100", "unreachable": 0, "loading": 0})
    assert outcome == "error"


def test_verdict_no_after_sample_is_an_error():
    outcome, reason = verdict(before={"nonce": "100", "unreachable": 1, "loading": 3}, after=None)
    assert outcome == "error"
    assert "no probe payload" in reason.lower() or "none" in reason.lower()


def test_verdict_banner_still_up_is_an_error():
    outcome, reason = verdict(
        before={"nonce": "100", "unreachable": 1, "loading": 3},
        after={"nonce": "100", "unreachable": 1, "loading": 0},
    )
    assert outcome == "error"
    assert "unreachable" in reason.lower() or "banner" in reason.lower()


def test_verdict_modules_still_loading_is_an_error():
    outcome, reason = verdict(
        before={"nonce": "100", "unreachable": 1, "loading": 3},
        after={"nonce": "100", "unreachable": 0, "loading": 1},
    )
    assert outcome == "error"
    assert "loading" in reason.lower()


def test_verdict_nonce_changed_is_an_error():
    # Recovered state, but a different page instance -- a reload, not a recovery.
    outcome, reason = verdict(
        before={"nonce": "100", "unreachable": 1, "loading": 3},
        after={"nonce": "200", "unreachable": 0, "loading": 0},
    )
    assert outcome == "error"
    assert "nonce" in reason.lower() or "instance" in reason.lower() or "reload" in reason.lower()
