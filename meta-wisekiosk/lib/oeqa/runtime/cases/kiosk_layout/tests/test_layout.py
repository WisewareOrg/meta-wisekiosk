"""Specifies cases/kiosk_layout/verdict.py: the probe's own `layout=<w>x<h>:<clear|overlap:<id>>`
title-line field (format fixed by the step-3 brief's own ruling, not invented here), parsed and
judged against the 720p floor (the ticket's "Decided": the display's designed layout renders
correctly at 720p or better, asserted at whatever mode xrandr reports).

parse_layout and verdict are split the same way kiosk_applied's case.py splits
_read_applied_sample from verdict: parse_layout only ever returns a dict or None, and verdict only
ever takes a dict -- the case checks for None itself before calling verdict, so verdict's own
contract never grows a None-handling branch of its own (judgement call, flagged to tree-impl).

No device, no DOM -- every title and parsed dict is constructed.
"""

import pytest

from oeqa.runtime.cases.kiosk_layout.verdict import parse_layout, verdict


@pytest.mark.parametrize(
    ("name", "title", "want"),
    [
        (
            "clear, at the floor exactly",
            "sCgdimfFxt:T | WK1 layout=1280x720:clear",
            {"width": 1280, "height": 720, "clear": True, "overlap_id": None},
        ),
        (
            "clear, above the floor",
            "sCgdimfFxt:T | WK1 layout=1920x1080:clear",
            {"width": 1920, "height": 1080, "clear": True, "overlap_id": None},
        ),
        (
            "a region overlapping the band, overlap_id carries its id",
            "sCgdimfFxt:T | WK1 layout=1280x720:overlap:top_left",
            {"width": 1280, "height": 720, "clear": False, "overlap_id": "top_left"},
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
        ("exactly at the floor, clear -- the boundary itself passes",
         {"width": 1280, "height": 720, "clear": True, "overlap_id": None}, "ok"),
        ("comfortably above the floor, clear",
         {"width": 1920, "height": 1080, "clear": True, "overlap_id": None}, "ok"),
        ("width below the floor", {"width": 1279, "height": 720, "clear": True, "overlap_id": None},
         "error"),
        ("height below the floor", {"width": 1280, "height": 719, "clear": True, "overlap_id": None},
         "error"),
        ("both below the floor", {"width": 640, "height": 480, "clear": True, "overlap_id": None},
         "error"),
        ("at the floor but a region overlaps the band",
         {"width": 1280, "height": 720, "clear": False, "overlap_id": "top_left"}, "error"),
    ],
)
def test_verdict_outcome(name, parsed, want_outcome):
    outcome, reason = verdict(parsed)
    assert outcome == want_outcome, f"{name}: {reason!r}"


def test_verdict_low_width_reason_names_the_dimension():
    outcome, reason = verdict({"width": 1000, "height": 720, "clear": True, "overlap_id": None})
    assert "width" in reason.lower()


def test_verdict_low_height_reason_names_the_dimension():
    outcome, reason = verdict({"width": 1280, "height": 600, "clear": True, "overlap_id": None})
    assert "height" in reason.lower()


def test_verdict_overlap_reason_names_the_overlapping_region():
    outcome, reason = verdict(
        {"width": 1280, "height": 720, "clear": False, "overlap_id": "bottom_right"})
    assert "bottom_right" in reason
