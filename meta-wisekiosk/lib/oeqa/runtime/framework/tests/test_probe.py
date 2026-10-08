"""Specifies oeqa/runtime/framework/probe.py: the title_lines/fields primitives every
case's own verdict.py parses from (docs/testing.md § "The render and applied cases").

No device, no DOM -- every xprop dump and title is constructed.
"""

from framework.probe import MARKER, WM_NAME, fields, title_lines

PROBE = "WK1 nonce=1 state=applied cards=-/- faulted=0 unreachable=0"


def test_marker_and_wm_name_are_the_one_spelling():
    # Not a behavior test -- just pins the constants every verdict.py now
    # imports rather than redefines (D2: five copies collapsed to one).
    assert MARKER == "WK1 "
    assert WM_NAME.match('WM_NAME(STRING) = "x"').group(1) == "x"


# --------------------------------------------------------------- title_lines

def test_title_lines_finds_every_window():
    xprop_output = (
        'WM_NAME(STRING) = "sCgdimfFxt:T | WiseKiosk"\n'
        f'WM_NAME(STRING) = "[42%] sCgdimfFxt:T | {PROBE}"\n'
    )
    assert title_lines(xprop_output) == [
        "sCgdimfFxt:T | WiseKiosk",
        f"[42%] sCgdimfFxt:T | {PROBE}",
    ]


def test_title_lines_empty_output_is_empty():
    assert title_lines("") == []


def test_title_lines_skips_a_line_with_no_wm_name_property():
    # xprop's real shape for a window with no WM_NAME property at all:
    # "WM_NAME:  not found." -- must be skipped, not stop the scan.
    xprop_output = (
        "WM_NAME:  not found.\n"
        f'WM_NAME(STRING) = "{PROBE}"\n'
    )
    assert title_lines(xprop_output) == [PROBE]


# -------------------------------------------------------------------- fields

def test_fields_finds_every_key_value_pair():
    assert fields(f"sCgdimfFxt:T | {PROBE}") == {
        "nonce": "1", "state": "applied", "cards": "-/-", "faulted": "0", "unreachable": "0",
    }


def test_fields_a_colon_bearing_value_is_not_truncated_at_the_colon():
    assert fields("WK1 state=error:not-app") == {"state": "error:not-app"}


def test_fields_no_marker_is_none():
    assert fields("sCgdimfFxt:T | WiseKiosk") is None


def test_fields_surfs_own_timing_payload_is_not_our_probe():
    assert fields("sCgdimfFxt:T | T 1763000000000 842") is None


def test_fields_empty_title_is_none():
    assert fields("") is None


def test_fields_marker_present_with_no_key_value_pairs_is_an_empty_dict():
    # The marker is present but nothing past it parses as key=value -- an
    # empty dict, not None: the payload is there, just carries no fields.
    assert fields("WK1 not-a-valid-payload-at-all") == {}


def test_fields_skips_a_malformed_token_with_no_equals():
    # Real, reachable input (surf's own title wrapping, or stray text past
    # the marker), not a value the probe itself emits maliciously.
    assert fields("WK1 garbage-with-no-equals-sign unreachable=1") == {"unreachable": "1"}
