"""Specifies cases/kiosk_layout/verdict.py: the mode `DISPLAY=:0 xrandr` reports, judged against
the 720p floor (the ticket's "Decided": the display runs at the configured mode, at or above the
design floor).

No device, no DOM -- every mode string and xrandr dump is constructed.
"""

import pytest

from oeqa.runtime.cases.kiosk_layout.verdict import pick_below_floor_mode, verdict


@pytest.mark.parametrize(
    ("name", "mode", "want_outcome"),
    [
        ("exactly at the floor -- the boundary itself passes", "1280x720", "ok"),
        ("comfortably above the floor", "1920x1080", "ok"),
        ("width below the floor", "1279x720", "error"),
        ("height below the floor", "1280x719", "error"),
        ("both below the floor", "640x480", "error"),
    ],
)
def test_verdict_outcome(name, mode, want_outcome):
    outcome, reason = verdict(mode)
    assert outcome == want_outcome, f"{name}: {reason!r}"


def test_verdict_low_width_reason_names_the_dimension():
    outcome, reason = verdict("1000x720")
    assert "width" in reason.lower()


def test_verdict_low_height_reason_names_the_dimension():
    outcome, reason = verdict("1280x600")
    assert "height" in reason.lower()


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
