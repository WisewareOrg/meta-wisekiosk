"""Specifies tests/verdicts/context.py: the device-context parsers conftest.py's
`device_context` fixture uses. Every case is a constructed string or bytes value -- no board,
no subprocess, no network.
"""

import pytest

from framework.record import keyed_hash
from verdicts.context import (
    asset_hashes,
    config_summary,
    kiosk_conf_mac,
    pid_from_pgrep,
    uptime_seconds,
    webkit_env,
)


# --------------------------------------------------------------------- uptime_seconds
# /proc/uptime's own shape: "<uptime> <idle>\n", both fields in seconds.

@pytest.mark.parametrize(
    ("name", "text", "want"),
    [
        ("typical uptime", "421.07 393.21\n", 421),
        ("just booted", "0.42 0.00\n", 0),
        ("no trailing newline", "123456.78 99999.99", 123456),
    ],
)
def test_uptime_seconds(name, text, want):
    assert uptime_seconds(text) == want, name


# --------------------------------------------------------------------- webkit_env
# Takes the whole (already NUL-to-newline-converted) /proc/<pid>/environ dump and
# filters WEBKIT_* lines itself.

def test_webkit_env_filters_and_joins_in_order():
    text = "HOME=/root\nWEBKIT_DISABLE_DMABUF_RENDERER=1\nPATH=/bin\nWEBKIT_FORCE_VBLANK_TIMER=1\n"
    assert webkit_env(text) == "WEBKIT_DISABLE_DMABUF_RENDERER=1,WEBKIT_FORCE_VBLANK_TIMER=1"


def test_webkit_env_none_present_is_empty():
    assert webkit_env("HOME=/root\nPATH=/bin\n") == ""


def test_webkit_env_empty_input_is_empty():
    assert webkit_env("") == ""


# ------------------------------------------------------------------ kiosk_conf_mac
# status is the ssh status of `cat /data/config/kiosk.conf`: 0 means the file was
# read, anything else means it does not exist (EnvironmentFile=- is optional).

def test_kiosk_conf_mac_present_is_keyed_hash_of_the_bytes():
    key, text = b"local-hmac-key", "KIOSK_URL=http://localhost:8080\n"
    assert kiosk_conf_mac(0, text, key) == keyed_hash(key, text.encode())


def test_kiosk_conf_mac_absent_is_the_literal_absent():
    assert kiosk_conf_mac(1, "cat: No such file or directory\n", b"local-hmac-key") == "absent"


# ------------------------------------------------------------------ pid_from_pgrep
# `pgrep -x surf`'s own shape: one pid per line. An empty result means no such
# process -- a named error, not an IndexError on an empty splitlines() list.

def test_pid_from_pgrep_first_line():
    assert pid_from_pgrep("1234\n") == "1234"


def test_pid_from_pgrep_takes_the_first_of_several():
    assert pid_from_pgrep("1234\n5678\n") == "1234"


def test_pid_from_pgrep_empty_raises():
    with pytest.raises(ValueError):
        pid_from_pgrep("")


# ------------------------------------------------------------------- asset_hashes
# Grounded in this tree's own built frontend bundle shape: a content-hash token is
# the dash-delimited segment before the file extension.

REAL_BUILT_INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <script type="module" crossorigin src="/assets/index-CDN2Arem.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-Bh0cOIYH.css">
  </head>
  <body><div id="app"></div></body>
</html>
"""


def test_asset_hashes_from_the_real_built_index_html():
    assert asset_hashes(REAL_BUILT_INDEX_HTML) == ["CDN2Arem", "Bh0cOIYH"]


def test_asset_hashes_takes_the_segment_after_the_last_dash():
    html = '<link rel="stylesheet" href="/assets/inter-latin-wght-normal-Dx4kXJAl.css">'
    assert asset_hashes(html) == ["Dx4kXJAl"]


def test_asset_hashes_none_is_empty():
    assert asset_hashes("<html><head></head><body></body></html>") == []


# ----------------------------------------------------------------- config_summary
# config.json's real shape (modules/region/options) with invented values -- never
# a real park name or a real coordinate. The app line carries config.json's
# location-free summary, no coordinate or park identifier -- so this is asserted
# by presence of the rest and absence of exactly those two leak vectors, never by
# its own exact serialisation.

INVENTED_CONFIG_JSON = """{
  "edge_band": 8,
  "modules": [
    {"region": "top_left", "module": "clock", "options": {"show_seconds": true}},
    {"region": "top_right", "module": "weather",
     "options": {"location": {"lat": 12.3456, "lon": -65.4321},
                 "series_switch_seconds": 10}},
    {"region": "bottom_left", "module": "park_wait_times",
     "options": {"parks": ["Example Park One", "Example Park Two"], "columns": 2}}
  ]
}"""


def test_config_summary_carries_modules_regions_and_intervals():
    summary = config_summary(INVENTED_CONFIG_JSON)
    for expect in ("clock", "weather", "park_wait_times", "top_left", "top_right",
                   "bottom_left", "series_switch_seconds", "10"):
        assert expect in summary, expect


def test_config_summary_excludes_coordinates_and_park_identifiers():
    summary = config_summary(INVENTED_CONFIG_JSON)
    for leak in ("12.3456", "-65.4321", "Example Park One", "Example Park Two"):
        assert leak not in summary, leak


def test_config_summary_has_no_raw_space():
    assert " " not in config_summary(INVENTED_CONFIG_JSON)
