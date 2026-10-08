"""Specifies cases/kiosk_layout/verdict.py: the probe's own `layout=<w>x<h>:<clear|overlap:<id>>
edge=<clear|unknown|<id>>` title-line fields (format fixed by the step-3 brief's own ruling, F3's
edge= addition round-1), parsed and judged against the 720p floor, band clearance and the
configured edge margin (the ticket's "Decided": the display's designed layout renders correctly at
720p or better, asserted at whatever mode xrandr reports).

parse_layout and verdict are split the same way kiosk_applied's case.py splits
_read_applied_sample from verdict: parse_layout only ever returns a dict or None, and verdict only
ever takes a dict -- the case checks for None itself before calling verdict, so verdict's own
contract never grows a None-handling branch of its own (judgement call, flagged to tree-impl).

No device, no DOM -- every title, parsed dict and xrandr dump is constructed.
"""

import pytest

from oeqa.runtime.cases.kiosk_layout.verdict import parse_layout, pick_below_floor_mode, verdict


@pytest.mark.parametrize(
    ("name", "title", "want"),
    [
        (
            "clear, at the floor exactly, edge clear",
            "sCgdimfFxt:T | WK1 layout=1280x720:clear edge=clear",
            {"width": 1280, "height": 720, "clear": True, "overlap_id": None, "edge": "clear"},
        ),
        (
            "clear, above the floor",
            "sCgdimfFxt:T | WK1 layout=1920x1080:clear edge=clear",
            {"width": 1920, "height": 1080, "clear": True, "overlap_id": None, "edge": "clear"},
        ),
        (
            "a region overlapping the band, overlap_id carries its id",
            "sCgdimfFxt:T | WK1 layout=1280x720:overlap:top_left edge=clear",
            {"width": 1280, "height": 720, "clear": False, "overlap_id": "top_left", "edge": "clear"},
        ),
        (
            "a region within the edge band, edge carries its id",
            "sCgdimfFxt:T | WK1 layout=1280x720:clear edge=bottom_right",
            {"width": 1280, "height": 720, "clear": True, "overlap_id": None, "edge": "bottom_right"},
        ),
        (
            "config.json not fetchable from the probe -- edge=unknown",
            "sCgdimfFxt:T | WK1 layout=1280x720:clear edge=unknown",
            {"width": 1280, "height": 720, "clear": True, "overlap_id": None, "edge": "unknown"},
        ),
        (
            "a layout= field predating the edge= extension defaults to unknown, never clear",
            "sCgdimfFxt:T | WK1 layout=1280x720:clear",
            {"width": 1280, "height": 720, "clear": True, "overlap_id": None, "edge": "unknown"},
        ),
        ("no layout field at all", "sCgdimfFxt:T | WK1 nonce=1 state=applied", None),
        ("empty title", "", None),
    ],
)
def test_parse_layout(name, title, want):
    assert parse_layout(title) == want, name


@pytest.mark.parametrize(
    ("name", "parsed", "want_outcome"),
    [
        ("exactly at the floor, clear, edge clear -- the boundary itself passes",
         {"width": 1280, "height": 720, "clear": True, "overlap_id": None, "edge": "clear"}, "ok"),
        ("comfortably above the floor, clear",
         {"width": 1920, "height": 1080, "clear": True, "overlap_id": None, "edge": "clear"}, "ok"),
        ("width below the floor",
         {"width": 1279, "height": 720, "clear": True, "overlap_id": None, "edge": "clear"}, "error"),
        ("height below the floor",
         {"width": 1280, "height": 719, "clear": True, "overlap_id": None, "edge": "clear"}, "error"),
        ("both below the floor",
         {"width": 640, "height": 480, "clear": True, "overlap_id": None, "edge": "clear"}, "error"),
        ("at the floor but a region overlaps the band",
         {"width": 1280, "height": 720, "clear": False, "overlap_id": "top_left", "edge": "clear"},
         "error"),
        ("at the floor, no overlap, but a region is within the edge band",
         {"width": 1280, "height": 720, "clear": True, "overlap_id": None, "edge": "bottom_right"},
         "error"),
        ("edge margin unconfirmed -- never a silent pass",
         {"width": 1280, "height": 720, "clear": True, "overlap_id": None, "edge": "unknown"},
         "error"),
    ],
)
def test_verdict_outcome(name, parsed, want_outcome):
    outcome, reason = verdict(parsed)
    assert outcome == want_outcome, f"{name}: {reason!r}"


def test_verdict_low_width_reason_names_the_dimension():
    outcome, reason = verdict(
        {"width": 1000, "height": 720, "clear": True, "overlap_id": None, "edge": "clear"})
    assert "width" in reason.lower()


def test_verdict_low_height_reason_names_the_dimension():
    outcome, reason = verdict(
        {"width": 1280, "height": 600, "clear": True, "overlap_id": None, "edge": "clear"})
    assert "height" in reason.lower()


def test_verdict_overlap_reason_names_the_overlapping_region():
    outcome, reason = verdict(
        {"width": 1280, "height": 720, "clear": False, "overlap_id": "bottom_right", "edge": "clear"})
    assert "bottom_right" in reason


def test_verdict_edge_reason_names_the_offending_element():
    outcome, reason = verdict(
        {"width": 1280, "height": 720, "clear": True, "overlap_id": None, "edge": "diagnosis"})
    assert "diagnosis" in reason


def test_verdict_edge_unknown_reason_names_why():
    outcome, reason = verdict(
        {"width": 1280, "height": 720, "clear": True, "overlap_id": None, "edge": "unknown"})
    assert "config.json" in reason


# ------------------------------------------------------------- pick_below_floor_mode
# A real `DISPLAY=:0 xrandr` capture from bench (round-1 fixes session, no address or
# other identity in it -- xrandr reports modes, never anything scrubbed elsewhere).

BENCH_XRANDR = """Screen 0: minimum 320 x 200, current 1280 x 720, maximum 2048 x 2048
HDMI-1 connected primary 1280x720+0+0 (normal left inverted right x axis y axis) 521mm x 293mm
   1920x1080     60.00 +  59.94
   1680x1050     59.88
   1280x1024     75.02    60.02
   1440x900      59.90
   1280x960      60.00
   1280x720      60.00*   59.94
   1024x768      75.03    70.07    60.00
   832x624       74.55
   800x600       72.19    75.00    60.32    56.25
   720x480       60.00    59.94
   640x480       75.00    72.81    66.67    60.00    59.94
   720x400       70.08
"""


def test_pick_below_floor_mode_real_bench_capture():
    # 1024x768 is below the floor (width 1024 < 1280) and the largest by
    # area among this connector's below-floor modes (786432 vs 832x624's
    # 519168 and smaller) -- not the one nearest 1280x720 textually.
    connector, current, candidate = pick_below_floor_mode(BENCH_XRANDR)
    assert connector == "HDMI-1"
    assert current == "1280x720"
    assert candidate == "1024x768"


NO_BELOW_FLOOR_XRANDR = """Screen 0: minimum 320 x 200, current 1920 x 1080, maximum 2048 x 2048
HDMI-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 521mm x 293mm
   1920x1080     60.00*+  59.94
   1680x1050     59.88
"""


def test_pick_below_floor_mode_connector_offers_none():
    connector, current, candidate = pick_below_floor_mode(NO_BELOW_FLOOR_XRANDR)
    assert connector == "HDMI-1"
    assert current == "1920x1080"
    assert candidate is None


def test_pick_below_floor_mode_no_connected_output():
    connector, current, candidate = pick_below_floor_mode(
        "Screen 0: minimum 320 x 200, current 1280 x 720, maximum 2048 x 2048\n"
        "HDMI-1 disconnected (normal left inverted right x axis y axis)\n"
    )
    assert connector is None
    assert current is None
    assert candidate is None


def test_pick_below_floor_mode_a_mode_line_with_no_x_is_skipped():
    # Defensive: real xrandr output never emits either shape, but a stray
    # line with no "x" in its first token, or an "x"-bearing token that
    # is not two digit groups, must not raise.
    connector, current, candidate = pick_below_floor_mode(
        "HDMI-1 connected primary 1280x720+0+0\n"
        "   not-a-mode\n"
        "   100xabc       60.00\n"
        "   1280x720      60.00*\n"
    )
    assert connector == "HDMI-1"
    assert current == "1280x720"
    assert candidate is None
