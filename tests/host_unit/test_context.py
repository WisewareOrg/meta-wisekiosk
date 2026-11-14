"""Specifies tests/verdicts/context.py: the device-context parsers over constructed text."""

import pytest

from verdicts.context import display_mode, file_hashes, webkit_env

_A = "a" * 64
_B = "b" * 64


def test_file_hashes_maps_each_path_to_its_hash():
    output = f"{_A}  /data/config/config.json\n{_B}  /boot/config.txt\n"
    assert file_hashes(output, ["/boot/config.txt", "/data/config/config.json"]) == {
        "/boot/config.txt": _B,
        "/data/config/config.json": _A,
    }


def test_file_hashes_absent_for_a_path_with_no_line():
    output = f"sha256sum: /data/config/kiosk.conf: No such file or directory\n{_A}  /boot/config.txt\n"
    assert file_hashes(output, ["/data/config/kiosk.conf", "/boot/config.txt"]) == {
        "/data/config/kiosk.conf": "absent",
        "/boot/config.txt": _A,
    }


XRANDR = """Screen 0: minimum 320 x 200, current 1280 x 720, maximum 8192 x 8192
HDMI-1 connected primary 1280x720+0+0 (normal left inverted right x axis y axis) 16in
   1920x1080     60.00 +  50.00
   1280x720      60.00*   59.94
   640x480       60.00
"""


def test_display_mode_from_the_starred_rate():
    assert display_mode(XRANDR) == "1280x720@60.00"


def test_display_mode_none_without_a_starred_rate():
    assert display_mode("HDMI-1 disconnected\n   1280x720      60.00   59.94\n") == "none"


def test_display_mode_none_for_empty_output():
    assert display_mode("") == "none"


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("HOME=/root\nWEBKIT_A=1\nPATH=/bin\nWEBKIT_B=2\n", "WEBKIT_A=1,WEBKIT_B=2"),
        ("HOME=/root\n", ""),
        ("", ""),
    ],
)
def test_webkit_env(text, want):
    assert webkit_env(text) == want
