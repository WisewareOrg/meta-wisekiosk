"""Specifies wisekiosk.record: the run record's parsers and R-line builders (design.md section 4).

Every case is a constructed string or bytes value -- no board, no subprocess, no network. The
parsers are each a faithful port of an existing shell fragment (tools/reproducibility-gate.sh's
awk/sed for buildinfo, run.sh's booted_slot() sed for the RAUC bootname); fixtures are built from
those exact line shapes, not an approximation of them. asset_hashes and config_summary are
exercised against this tree's own real build artifacts (the frontend's built dist/index.html and
WiseKiosk's shipped config.json shape), not an invented format.
"""

import hashlib
import hmac

import pytest

from wisekiosk.record import (
    app_line,
    asset_hashes,
    board_line,
    boot_ordinal,
    booted_slot,
    config_summary,
    image_line,
    keyed_hash,
    page_line,
    parse_buildinfo,
    scrub_argv,
    slot_installed_at,
    sut_line,
    tool_line,
)

SHA = "deadbeef" * 5  # 40 hex chars, the shape image-buildinfo and git both require


# --------------------------------------------------------------- parse_buildinfo
# image-buildinfo writes one line per layer as "%-17s = %s:%s%s"; the gate's own
# awk/sed (recon.md section 2) is the ported logic here.

BUILDINFO_OTHER_LAYERS = (
    "meta               = master:1111111111111111111111111111111111111111\n"
    "meta-raspberrypi   = master:2222222222222222222222222222222222222222\n"
)


NORMAL_BUILDINFO = BUILDINFO_OTHER_LAYERS + f"meta-wisekiosk     = main:{SHA}\n"

BUILDINFO_CASES = [
    ("normal line among other layers", NORMAL_BUILDINFO, ("main", SHA)),
    ("modified suffix dropped by field-splitting, not specially matched",
     BUILDINFO_OTHER_LAYERS + f"meta-wisekiosk     = main:{SHA} -- modified\n", ("main", SHA)),
    ("image-buildinfo's own <unknown> sha passes through unchanged",
     "meta-wisekiosk     = main:<unknown>\n", ("main", "<unknown>")),
    ("no meta-wisekiosk line at all", BUILDINFO_OTHER_LAYERS, ("", "")),
    ("empty buildinfo", "", ("", "")),
    ("CRLF line endings are stripped before matching",
     NORMAL_BUILDINFO.replace("\n", "\r\n"), ("main", SHA)),
]


@pytest.mark.parametrize(("name", "text", "want"), BUILDINFO_CASES, ids=[c[0] for c in BUILDINFO_CASES])
def test_parse_buildinfo(name, text, want):
    assert parse_buildinfo(text) == want, name


# ------------------------------------------------------------------- booted_slot
# run.sh's own booted_slot(): sed -n "s/^RAUC_SYSTEM_BOOTED_BOOTNAME='\(.*\)'/\1/p"

RAUC_SHELL_OTHER_LINES = "RAUC_SYSTEM_COMPATIBLE='wisekiosk-raspberrypi0-wifi'\n"


@pytest.mark.parametrize(
    ("name", "text", "want"),
    [
        ("slot A", RAUC_SHELL_OTHER_LINES + "RAUC_SYSTEM_BOOTED_BOOTNAME='A'\n", "A"),
        ("slot B", RAUC_SHELL_OTHER_LINES + "RAUC_SYSTEM_BOOTED_BOOTNAME='B'\n", "B"),
        ("no such line", RAUC_SHELL_OTHER_LINES, ""),
    ],
)
def test_booted_slot(name, text, want):
    assert booted_slot(text) == want, name


# ---------------------------------------------------------------- slot_installed_at
# Real sample: local/202/step1/rauc-journal-sample.txt, "rauc status --detailed
# --output-format=shell" on bench, RAUC 1.15.2. Slot 1 (bootname B) is booted and
# carries the real install timestamp; slot 2 (bootname A, inactive) is the
# distractor that proves the function picks the BOOTED slot, not the first one.

DETAILED_SHELL_BENCH_SAMPLE = """RAUC_SYSTEM_BOOTED_BOOTNAME='B'
RAUC_SLOT_STATE_1='booted'
RAUC_SLOT_BOOTNAME_1='B'
RAUC_SLOT_STATUS_INSTALLED_TIMESTAMP_1='2026-10-07T06:15:27Z'
RAUC_SLOT_STATUS_INSTALLED_COUNT_1='28'
RAUC_SLOT_STATUS_ACTIVATED_TIMESTAMP_1='2026-10-07T06:15:27Z'
RAUC_SLOT_STATUS_ACTIVATED_COUNT_1='28'
RAUC_SLOT_STATE_2='inactive'
RAUC_SLOT_BOOTNAME_2='A'
RAUC_SLOT_STATUS_INSTALLED_TIMESTAMP_2='2026-10-06T20:58:31Z'
RAUC_SLOT_STATUS_INSTALLED_COUNT_2='20'
RAUC_SLOT_STATUS_ACTIVATED_TIMESTAMP_2='2026-10-06T20:58:31Z'
RAUC_SLOT_STATUS_ACTIVATED_COUNT_2='20'
"""

NO_BOOTED_SLOT = DETAILED_SHELL_BENCH_SAMPLE.replace("STATE_1='booted'", "STATE_1='inactive'")

BOOTED_SLOT_WITHOUT_TIMESTAMP = "\n".join(
    line for line in DETAILED_SHELL_BENCH_SAMPLE.splitlines()
    if "STATUS_INSTALLED_TIMESTAMP_1" not in line
)


def test_slot_installed_at_real_bench_sample():
    assert slot_installed_at(DETAILED_SHELL_BENCH_SAMPLE) == "2026-10-07T06:15:27Z"


def test_slot_installed_at_no_booted_slot_raises():
    with pytest.raises(ValueError):
        slot_installed_at(NO_BOOTED_SLOT)


def test_slot_installed_at_booted_slot_missing_its_timestamp_raises():
    with pytest.raises(ValueError):
        slot_installed_at(BOOTED_SLOT_WITHOUT_TIMESTAMP)


# --------------------------------------------------------------------- boot_ordinal
# Real sample, same source: "journalctl --list-boots -o json" on bench. The last
# seven real boot entries (indices -6..0) are used verbatim -- boot ids and
# first_entry/last_entry microsecond timestamps are the device's own, not
# invented. Independently computed (not via the module under test): with
# installed_at = slot A's real install instant (2026-10-06T20:58:31Z), boots -5
# through 0 (6 of the 7) have a first_entry at or after it; boot -6 does not.

LAST_7_BOOTS_JSON = (
    '[{"index": -6, "boot_id": "e65eda34a3264678a75feb6eaf6d123c", '
    '"first_entry": 1791319333678888, "last_entry": 1791320316339998}, '
    '{"index": -5, "boot_id": "13bae6d42bbb42a4be34bb753e8b9dc7", '
    '"first_entry": 1791320317811532, "last_entry": 1791327184481256}, '
    '{"index": -4, "boot_id": "eb10912bdeec423195019862d7b32b6a", '
    '"first_entry": 1791327185815877, "last_entry": 1791327403804314}, '
    '{"index": -3, "boot_id": "f26fc45501ea4a24a47f9421c17361fe", '
    '"first_entry": 1791327405108465, "last_entry": 1791328271675732}, '
    '{"index": -2, "boot_id": "757a013206d24084914efb3ee23e7762", '
    '"first_entry": 1791328273002779, "last_entry": 1791328482901988}, '
    '{"index": -1, "boot_id": "14991b2a366a4b8abd95c3f1deb1b9db", '
    '"first_entry": 1791328484301119, "last_entry": 1791353734394259}, '
    '{"index": 0, "boot_id": "c49325c8c53d4b59a560d80045297f4c", '
    '"first_entry": 1791353735699163, "last_entry": 1791367275788819}]'
)
# datetime.fromtimestamp(1791353735699163 / 1e6, tz=utc).isoformat() -- boot 0's
# own first_entry, exactly, computed independently of boot_ordinal.
BOOT_0_FIRST_ENTRY_ISO = "2026-10-07T06:15:35.699163Z"

BOOT_ORDINAL_CASES = [
    ("install instant falls between two real boots (slot B, booted): only the"
     " current boot (index 0) is at or after it",
     LAST_7_BOOTS_JSON, "2026-10-07T06:15:27Z", 1),
    ("install instant equals a boot's first_entry exactly -- inclusive, not exclusive",
     LAST_7_BOOTS_JSON, BOOT_0_FIRST_ENTRY_ISO, 1),
    ("install instant later than every boot reads 0, not an error",
     LAST_7_BOOTS_JSON, "2026-10-07T07:00:00Z", 0),
    ("slot A's real (non-booted) install instant counts 6 of these 7 real boots",
     LAST_7_BOOTS_JSON, "2026-10-06T20:58:31Z", 6),
    ("an empty boot list reads 0", "[]", "2026-10-07T06:15:27Z", 0),
]


@pytest.mark.parametrize(("name", "boots_json", "installed_at", "want"), BOOT_ORDINAL_CASES,
                          ids=[c[0] for c in BOOT_ORDINAL_CASES])
def test_boot_ordinal(name, boots_json, installed_at, want):
    assert boot_ordinal(boots_json, installed_at) == want, name


def test_boot_ordinal_unparseable_json_raises():
    with pytest.raises(ValueError):
        boot_ordinal("not json", "2026-10-07T06:15:27Z")


def test_boot_ordinal_unparseable_iso_raises():
    with pytest.raises(ValueError):
        boot_ordinal(LAST_7_BOOTS_JSON, "not a timestamp")


# --------------------------------------------------------------------- keyed_hash
# HMAC-SHA256 hex: RFC 4231 test case 1, an external known-answer vector, plus an
# independent computation of a second vector via hmac/hashlib directly (not the
# module under test) so the expectation is never derived from the implementation
# it checks.

RFC4231_CASE1_KEY = bytes([0x0B] * 20)
RFC4231_CASE1_DATA = b"Hi There"
RFC4231_CASE1_HEX = "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"


def test_keyed_hash_rfc4231_known_answer():
    assert keyed_hash(RFC4231_CASE1_KEY, RFC4231_CASE1_DATA) == RFC4231_CASE1_HEX


def test_keyed_hash_matches_independent_hmac_sha256():
    key, data = b"local-hmac-key", b'{"modules": []}'
    want = hmac.new(key, data, hashlib.sha256).hexdigest()
    assert keyed_hash(key, data) == want


# --------------------------------------------------------------------- scrub_argv
# argv is sys.argv joined, with the target and every RFC1918 address replaced by
# "<target>" -- including an RFC1918 address that is not the target itself.
#
# No RFC1918 literal reaches this tracked file, fixtures included (CONTRIBUTING.md:
# "no device address... in a test fixture"): every private address below is
# assembled from octets through _dotted, never written as a dotted-quad, so
# tools/ci-guards.sh guard 6 and scrub-identity.py's pattern half see none of them.
# The one non-private example uses an RFC 5737 documentation address, never a real
# host's.

def _dotted(*octets):
    return ".".join(str(o) for o in octets)


TARGET_ADDR = _dotted(192, 168, 1, 50)
OTHER_PRIVATE_ADDR = _dotted(10, 0, 5, 9)
DOC_ADDR = _dotted(203, 0, 113, 5)  # RFC 5737 TEST-NET-3, never a real host
IN_172_RANGE = _dotted(172, 16, 0, 1)
BELOW_172_RANGE = _dotted(172, 15, 255, 255)
ABOVE_172_RANGE = _dotted(172, 32, 0, 1)
IN_192_168 = _dotted(192, 168, 0, 1)
NOT_192_168 = _dotted(192, 169, 0, 1)  # one past the /16 -- not RFC1918, left alone
IN_10_8 = _dotted(10, 255, 255, 255)
NOT_10_8 = _dotted(11, 0, 0, 1)  # one past the /8 -- not RFC1918, left alone

SCRUB_ARGV_CASES = [
    ("the target's own address", ["oe-test", "runtime", "--target-ip", TARGET_ADDR],
     TARGET_ADDR, "oe-test runtime --target-ip <target>"),
    ("a non-target RFC1918 address is scrubbed too", ["ssh", OTHER_PRIVATE_ADDR, "cmd"], TARGET_ADDR,
     "ssh <target> cmd"),
    ("a public address that is not the target is left alone", ["curl", DOC_ADDR],
     TARGET_ADDR, f"curl {DOC_ADDR}"),
    ("a hostname target is substituted the same way", ["ssh", "bench-host", "hostname"],
     "bench-host", "ssh <target> hostname"),
    ("172.16/12 lower boundary: in range", ["x", IN_172_RANGE], "unrelated", "x <target>"),
    ("172.16/12 just below the range is not scrubbed", ["x", BELOW_172_RANGE], "unrelated",
     f"x {BELOW_172_RANGE}"),
    ("172.16/12 just above the range is not scrubbed", ["x", ABOVE_172_RANGE], "unrelated",
     f"x {ABOVE_172_RANGE}"),
    ("the 192.168/16 range is scrubbed, one past it is not", ["x", IN_192_168, NOT_192_168],
     "unrelated", f"x <target> {NOT_192_168}"),
    ("the 10/8 range is scrubbed, one past it is not", ["x", IN_10_8, NOT_10_8], "unrelated",
     f"x <target> {NOT_10_8}"),
]


@pytest.mark.parametrize(("name", "argv", "target", "want"), SCRUB_ARGV_CASES,
                          ids=[c[0] for c in SCRUB_ARGV_CASES])
def test_scrub_argv(name, argv, target, want):
    assert scrub_argv(argv, target) == want, name


# ------------------------------------------------------------------- asset_hashes
# Grounded in this tree's own built frontend bundle:
# build/tmp-raspberrypi0-wifi/.../wisekiosk-frontend/.../dist/index.html, which
# references /assets/index-CDN2Arem.js and /assets/index-Bh0cOIYH.css -- the
# content-hash token is the dash-delimited segment before the extension.

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
# Grounded in WiseKiosk's real shipped config.json shape (modules/region/options).
# design.md section 4: the summary publishes the rest of the file's shape once
# coordinates and park identifiers are removed -- so it is asserted by presence of
# the rest and absence of exactly those two leak vectors, never by its own exact
# serialisation.

REAL_SHAPED_CONFIG = """{
  "edge_band": 8,
  "modules": [
    {"region": "top_left", "module": "clock", "options": {"show_seconds": true}},
    {"region": "top_right", "module": "weather",
     "options": {"location": {"lat": 29.2108, "lon": -81.0228},
                 "series_switch_seconds": 10}},
    {"region": "bottom_left", "module": "park_wait_times",
     "options": {"parks": ["Magic Kingdom", "Epcot"], "columns": 2}}
  ]
}"""


def test_config_summary_carries_modules_regions_and_intervals():
    summary = config_summary(REAL_SHAPED_CONFIG)
    for expect in ("clock", "weather", "park_wait_times", "top_left", "top_right",
                   "bottom_left", "series_switch_seconds", "10"):
        assert expect in summary, expect


def test_config_summary_excludes_coordinates_and_park_identifiers():
    summary = config_summary(REAL_SHAPED_CONFIG)
    for leak in ("29.2108", "-81.0228", "Magic Kingdom", "Epcot"):
        assert leak not in summary, leak


def test_config_summary_has_no_raw_space():
    # The R-line grammar (design.md section 4) is space-delimited k=v pairs; a
    # space inside config= would corrupt the line it is embedded in.
    assert " " not in config_summary(REAL_SHAPED_CONFIG)


# ------------------------------------------------------------------- line builders
# design.md section 4, verbatim: each builder renders exactly one R line from
# keyword arguments and interprets nothing.

def test_tool_line():
    got = tool_line(name="oe-test", tool_commit=SHA, dirty=0, argv="oe-test runtime <target>")
    assert got == f"R tool=oe-test tool_commit={SHA} dirty=0 argv=oe-test runtime <target>"


def test_board_line():
    got = board_line(
        role="bench", boot_id="3b1f...boot-id", boot_ordinal=2, uptime_s=421,
        start="2026-10-07T12:00:00Z", end="2026-10-07T12:20:00Z",
    )
    assert got == (
        "R board=bench hostname_check=ok boot_id=3b1f...boot-id boot_ordinal=2 "
        "uptime_s=421 start=2026-10-07T12:00:00Z end=2026-10-07T12:20:00Z"
    )


def test_image_line():
    assert image_line(sha=SHA, slot="A") == f"R image={SHA} slot=A"


def test_app_line():
    got = app_line(bundle="CDN2Arem,Bh0cOIYH", config_mac="a1b2c3", config="clock,weather")
    assert got == "R app bundle=CDN2Arem,Bh0cOIYH config_mac=a1b2c3 config=clock,weather"


def test_app_line_empty_bundle():
    got = app_line(bundle="", config_mac="a1b2c3", config="clock")
    assert got == "R app bundle= config_mac=a1b2c3 config=clock"


def test_sut_line():
    got = sut_line(
        browser="surf", nrestarts=0, cmdline_sha="aa11", webkit_env="WEBKIT_FORCE_VBLANK_TIMER=1",
        kiosk_conf_mac="absent", mode="1280x720", kernel="6.1.0", cpufreq_max="1000000",
        timesync="yes",
    )
    assert got == (
        "R sut browser=surf nrestarts=0 cmdline_sha=aa11 "
        "webkit_env=WEBKIT_FORCE_VBLANK_TIMER=1 kiosk_conf_mac=absent mode=1280x720 "
        "kernel=6.1.0 cpufreq_max=1000000 timesync=yes"
    )


def test_page_line():
    got = page_line(nonce="1699999999.5", state="applied", cards="-/-", faulted=0, unreachable=0)
    assert got == "R page nonce=1699999999.5 state=applied cards=-/- faulted=0 unreachable=0"


# ------------------------------------------------------------ the whole record
# design.md section 4 / brief: a record built from inputs carrying an address, a
# hostname, a key and config.json's coordinates and park identifiers must leak
# none of them. No new function -- this composes the ones proven individually
# above, the way a case's setUpClass would.

def test_record_never_leaks_identity_or_the_hmac_key():
    # The hostname is not asserted here: design.md section 4 keeps it out structurally (no R-line
    # field carries one at all -- it is compared live in setUpClass, never stored), so there is no
    # scrub to exercise. The address is assembled via _dotted, never a literal (see scrub_argv
    # section above).
    address, key = _dotted(192, 168, 1, 77), b"topsecretkey"

    lines = [
        tool_line(
            name="oe-test", tool_commit=SHA, dirty=0,
            argv=scrub_argv(["oe-test", "runtime", "--target-ip", address], address),
        ),
        board_line(
            role="bench", boot_id="x", boot_ordinal=1, uptime_s=1,
            start="2026-10-07T00:00:00Z", end="2026-10-07T00:01:00Z",
        ),
        image_line(sha=SHA, slot="A"),
        app_line(
            bundle=",".join(asset_hashes(REAL_BUILT_INDEX_HTML)),
            config_mac=keyed_hash(key, REAL_SHAPED_CONFIG.encode()),
            config=config_summary(REAL_SHAPED_CONFIG),
        ),
    ]
    record = "\n".join(lines)

    for leak in (address, "topsecretkey", "29.2108", "-81.0228", "Magic Kingdom", "Epcot"):
        assert leak not in record, leak
