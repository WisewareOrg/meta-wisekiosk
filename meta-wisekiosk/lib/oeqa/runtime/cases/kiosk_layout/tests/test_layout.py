"""Specifies cases/kiosk_layout/verdict.py: the mode `DISPLAY=:0 xrandr` reports, judged against
the 720p floor and the launcher's own configured mode.

No device, no DOM -- every mode string and xrandr dump is constructed.
"""

import pytest

from oeqa.runtime.cases.kiosk_layout.verdict import current_mode, pick_below_floor_mode, verdict

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


def test_current_mode_finds_the_starred_line():
    assert current_mode(BENCH_XRANDR) == "1280x720"


def test_current_mode_none_when_no_line_is_current():
    assert current_mode("HDMI-1 connected primary 1280x720+0+0\n   1280x720      60.00\n") is None


def test_current_mode_skips_a_malformed_marked_line():
    # Defensive: real xrandr output never emits this shape, but a stray "*"
    # on a line whose first token is not "<w>x<h>" must not raise.
    xrandr_output = "   not-a-mode*\n   1280x720      60.00*\n"
    assert current_mode(xrandr_output) == "1280x720"


@pytest.mark.parametrize(
    ("name", "xrandr_output", "configured_mode", "want_outcome"),
    [
        ("exactly at the floor, matching configured -- the boundary itself passes",
         BENCH_XRANDR, "1280x720", "ok"),
        ("a width below the floor",
         "HDMI-1 connected primary 1279x720+0+0\n   1279x720      60.00*\n", "1279x720",
         "below-floor"),
        ("a height below the floor",
         "HDMI-1 connected primary 1280x719+0+0\n   1280x719      60.00*\n", "1280x719",
         "below-floor"),
        ("clears the floor but does not match the configured mode",
         "HDMI-1 connected primary 1920x1080+0+0\n   1920x1080      60.00*\n", "1280x720",
         "mode-mismatch"),
        ("no current mode at all",
         "HDMI-1 connected primary 1280x720+0+0\n", "1280x720", "error"),
    ],
)
def test_verdict_outcome(name, xrandr_output, configured_mode, want_outcome):
    outcome, reason = verdict(xrandr_output, configured_mode)
    assert outcome == want_outcome, f"{name}: {reason!r}"


def test_verdict_error_reason_names_why():
    outcome, reason = verdict("HDMI-1 connected primary 1280x720+0+0\n", "1280x720")
    assert "no current mode" in reason


def test_verdict_mode_mismatch_reason_names_both_modes():
    outcome, reason = verdict(
        "HDMI-1 connected primary 1920x1080+0+0\n   1920x1080      60.00*\n", "1280x720")
    assert "1920x1080" in reason and "1280x720" in reason


# ------------------------------------------------------------- pick_below_floor_mode
# A real `DISPLAY=:0 xrandr` capture from bench (no address or other identity in it --
# xrandr reports modes, never anything scrubbed elsewhere).

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


def test_pick_below_floor_mode_a_blank_indented_line_is_skipped():
    # Defensive: real xrandr output never emits a whitespace-only indented
    # line, but one must not raise on an empty split().
    connector, current, candidate = pick_below_floor_mode(
        "HDMI-1 connected primary 1280x720+0+0\n"
        "   \n"
        "   1280x720      60.00*\n"
    )
    assert connector == "HDMI-1"
    assert current == "1280x720"
    assert candidate is None


def test_pick_below_floor_mode_a_non_numeric_mode_token_is_skipped():
    # Defensive: real xrandr output never emits this shape, but a stray
    # "<w>x<non-digit>" token must not raise.
    connector, current, candidate = pick_below_floor_mode(
        "HDMI-1 connected primary 1280x720+0+0\n"
        "   100xabc       60.00\n"
        "   1280x720      60.00*\n"
    )
    assert connector == "HDMI-1"
    assert current == "1280x720"
    assert candidate is None


def test_pick_below_floor_mode_no_connected_output():
    connector, current, candidate = pick_below_floor_mode(
        "Screen 0: minimum 320 x 200, current 1280 x 720, maximum 2048 x 2048\n"
        "HDMI-1 disconnected (normal left inverted right x axis y axis)\n"
    )
    assert connector is None
    assert current is None
    assert candidate is None
