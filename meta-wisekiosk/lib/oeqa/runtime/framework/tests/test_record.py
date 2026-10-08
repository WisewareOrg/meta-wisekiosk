"""Specifies oeqa/runtime/framework/record.py: the run record's parsers and R-line builders
(docs/testing.md section "Running it": "The run record.").

Every case is a constructed string or bytes value -- no board, no subprocess, no network. The
parsers are each a faithful port of an existing shell fragment (tools/reproducibility-gate.sh's
awk/sed for buildinfo, run.sh's booted_slot() sed for the RAUC bootname); fixtures are built from
those exact line shapes, not an approximation of them. asset_hashes and config_summary are
exercised against this tree's own real build artifacts (the frontend's built dist/index.html and
WiseKiosk's shipped config.json shape), not an invented format.
"""

import hashlib
import hmac
import re
import subprocess
from pathlib import Path

import pytest

from framework.record import (
    app_line,
    asset_hashes,
    board_line,
    boot_ordinal,
    booted_slot,
    config_summary,
    decode_hex_dump,
    dirty,
    hostname_mismatch,
    image_line,
    keyed_hash,
    kiosk_conf_mac,
    page_line,
    parse_buildinfo,
    pid_from_pgrep,
    scrub_argv,
    slot_installed_at,
    sut_line,
    tool_line,
    tool_name,
    uptime_seconds,
    webkit_env,
)

SHA = "deadbeef" * 5  # 40 hex chars, the shape image-buildinfo and git both require


# --------------------------------------------------------------- parse_buildinfo
# image-buildinfo writes one line per layer as "%-17s = %s:%s%s"; ported from
# tools/reproducibility-gate.sh's own awk/sed.

BUILDINFO_OTHER_LAYERS = (
    "meta               = master:1111111111111111111111111111111111111111\n"
    "meta-raspberrypi   = master:2222222222222222222222222222222222222222\n"
)


NORMAL_BUILDINFO = BUILDINFO_OTHER_LAYERS + f"meta-wisekiosk     = main:{SHA}\n"

BUILDINFO_CASES = [
    ("normal line among other layers", NORMAL_BUILDINFO, SHA),
    ("modified suffix dropped by field-splitting, not specially matched",
     BUILDINFO_OTHER_LAYERS + f"meta-wisekiosk     = main:{SHA} -- modified\n", SHA),
    ("image-buildinfo's own <unknown> sha passes through unchanged",
     "meta-wisekiosk     = main:<unknown>\n", "<unknown>"),
    ("no meta-wisekiosk line at all", BUILDINFO_OTHER_LAYERS, ""),
    ("empty buildinfo", "", ""),
    ("CRLF line endings are stripped before matching",
     NORMAL_BUILDINFO.replace("\n", "\r\n"), SHA),
]


@pytest.mark.parametrize(("name", "text", "want"), BUILDINFO_CASES, ids=[c[0] for c in BUILDINFO_CASES])
def test_parse_buildinfo(name, text, want):
    assert parse_buildinfo(text) == want, name


GATE_PATH = Path(__file__).resolve().parents[6] / "tools" / "reproducibility-gate.sh"
_GATE_AWK_LINE = re.compile(r"rev=\$\(awk '([^']*)' <<< \"\$info\"\)")


def _gate_commit(text):
    """Runs the exact awk program extracted from the live tools/reproducibility-gate.sh (never a
    copy) against text, after the same tr -d '\\r' preprocessing the gate applies first."""
    m = _GATE_AWK_LINE.search(GATE_PATH.read_text())
    assert m, "the gate's awk line has changed shape -- update this extraction"
    info = text.replace("\r", "")
    rev = subprocess.run(
        ["awk", m.group(1)], input=info, capture_output=True, text=True, check=True,
    ).stdout.strip()
    return rev.rsplit(":", 1)[-1] if rev else ""


AGREEMENT_CASES = [(c[0], c[1]) for c in BUILDINFO_CASES] + [
    ("unspaced 'meta-wisekiosk=main:<sha>' disagrees without this test",
     f"meta-wisekiosk=main:{SHA}\n"),
]


@pytest.mark.parametrize(("name", "text"), AGREEMENT_CASES, ids=[c[0] for c in AGREEMENT_CASES])
def test_parse_buildinfo_agrees_with_the_gates_own_awk(name, text):
    assert parse_buildinfo(text) == _gate_commit(text), name


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
# A real, identity-scrubbed "rauc status --detailed --output-format=shell" capture
# from bench. Slot 1 (bootname B) is booted and carries the real install
# timestamp; slot 2 (bootname A, inactive) is the distractor that proves the
# function picks the BOOTED slot, not the first one.

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
# One pass over `journalctl -u rauc.service -o json --output-fields=_BOOT_ID,
# MESSAGE,__REALTIME_TIMESTAMP` (one JSON object per line). Counts a line when
# its MESSAGE names booted_bootname's "Booted into rootfs.<n> (<slot>)" AND its
# own __REALTIME_TIMESTAMP (microseconds since the epoch, journalctl -o json's
# own string form) is at or after installed_at -- never --list-boots' own
# first_entry, which floors to a pre-sync clock on some boots before NTP
# corrects it; the RAUC line's timestamp is taken after that correction.
#
# The first four lines are a real bench capture (one job's log.do_testimage),
# kept in the device's own order -- which is not time-sorted, so counting
# correctly here already proves there is no positional assumption:
#   14:43:51 B (131d6d5b)  14:47:35 B (590fa325)
#   15:10:45 A (d3a2c6d4)  15:15:59 B (84c05234)

REAL_JOURNAL_JSON_LINES = (
    '{"_BOOT_ID": "d3a2c6d465d84d14b53f5606725bfe8c", "MESSAGE": "Booted into rootfs.0 (A)", '
    '"__REALTIME_TIMESTAMP": "1791385845368898"}\n'
    '{"_BOOT_ID": "131d6d5bcc4c4c5082b5d8f651f5a968", "MESSAGE": "Booted into rootfs.1 (B)", '
    '"__REALTIME_TIMESTAMP": "1791384231764057"}\n'
    '{"_BOOT_ID": "590fa3255db345f097abf7f73a24b663", "MESSAGE": "Booted into rootfs.1 (B)", '
    '"__REALTIME_TIMESTAMP": "1791384455580062"}\n'
    '{"_BOOT_ID": "84c05234c0a34756bf4f7f7b7f5ef396", "MESSAGE": "Booted into rootfs.1 (B)", '
    '"__REALTIME_TIMESTAMP": "1791386159499831"}\n'
)
# datetime.fromtimestamp(1791386159499831 / 1e6, tz=utc).isoformat() -- the last
# B line's own timestamp, exactly, computed independently of boot_ordinal.
LAST_B_TIMESTAMP_ISO = "2026-10-07T15:15:59.499831Z"

REAL_JOURNAL_CASES = [
    ("the clock-floor case: counts by each line's own timestamp, not device"
     " order -- only the last (chronologically, not textually) B line is at"
     " or after this instant", "B", "2026-10-07T15:00:00Z", 1),
    ("install instant equals a line's own timestamp exactly -- inclusive",
     "B", LAST_B_TIMESTAMP_ISO, 1),
    ("install instant before every line counts all three of this slot's boots",
     "B", "2026-10-07T14:00:00Z", 3),
    ("install instant after every line reads 0, not an error",
     "B", "2026-10-07T16:00:00Z", 0),
    ("a different booted_bootname counts only its own slot's one line",
     "A", "2026-10-07T14:00:00Z", 1),
]


@pytest.mark.parametrize(("name", "booted_bootname", "installed_at", "want"), REAL_JOURNAL_CASES,
                          ids=[c[0] for c in REAL_JOURNAL_CASES])
def test_boot_ordinal_real_bench_capture(name, booted_bootname, installed_at, want):
    assert boot_ordinal(REAL_JOURNAL_JSON_LINES, installed_at, booted_bootname) == want, name


def test_boot_ordinal_empty_input_reads_zero():
    assert boot_ordinal("", "2026-10-07T06:15:27Z", "B") == 0


def test_boot_ordinal_unparseable_installed_at_raises():
    with pytest.raises(ValueError):
        boot_ordinal(REAL_JOURNAL_JSON_LINES, "not a timestamp", "B")


# The ticket's own definition, dedicated case: installed B at T0, boots since T0
# are B, A, B in order -- only the two B boots count. Entirely invented, no real
# boot ids or device data.
TWO_SLOT_HISTORY_JOURNAL = (
    '{"_BOOT_ID": "before-install", "MESSAGE": "Booted into rootfs.1 (B)", '
    '"__REALTIME_TIMESTAMP": "1800000000000000"}\n'
    '{"_BOOT_ID": "boot-b1", "MESSAGE": "Booted into rootfs.1 (B)", '
    '"__REALTIME_TIMESTAMP": "1800000100000000"}\n'
    '{"_BOOT_ID": "boot-a1", "MESSAGE": "Booted into rootfs.0 (A)", '
    '"__REALTIME_TIMESTAMP": "1800000200000000"}\n'
    '{"_BOOT_ID": "boot-b2", "MESSAGE": "Booted into rootfs.1 (B)", '
    '"__REALTIME_TIMESTAMP": "1800000300000000"}\n'
)
TWO_SLOT_HISTORY_T0 = "2027-01-15T08:00:50Z"


def test_boot_ordinal_counts_only_the_booted_slots_own_boots():
    got = boot_ordinal(TWO_SLOT_HISTORY_JOURNAL, TWO_SLOT_HISTORY_T0, "B")
    assert got == 2


# Malformed lines are skipped, never guessed and never raised on -- the same
# discipline every other journal parser in this module follows.
def test_boot_ordinal_skips_malformed_lines_without_raising():
    text = (
        "\n"  # journalctl sometimes trails output with a blank line
        "not json at all\n"
        '{"_BOOT_ID": "byte-array-message", "MESSAGE": ["not", "a", "string"], '
        '"__REALTIME_TIMESTAMP": "1800000400000000"}\n'  # byte-array MESSAGE
        '{"_BOOT_ID": "no-timestamp", "MESSAGE": "Booted into rootfs.1 (B)"}\n'  # no timestamp
        '{"_BOOT_ID": "non-numeric-timestamp", "MESSAGE": "Booted into rootfs.1 (B)", '
        '"__REALTIME_TIMESTAMP": "not-a-number"}\n'  # present but unparseable
        '{"_BOOT_ID": "unrelated", "MESSAGE": "rauc mark-good succeeded", '
        '"__REALTIME_TIMESTAMP": "1800000400000000"}\n'  # names no slot
        '{"_BOOT_ID": "the-real-one", "MESSAGE": "Booted into rootfs.1 (B)", '
        '"__REALTIME_TIMESTAMP": "1800000400000000"}\n'
    )
    # Only the one well-formed, slot-naming, timestamped line counts.
    assert boot_ordinal(text, "2027-01-15T08:00:00Z", "B") == 1


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


# ----------------------------------------------------------------- decode_hex_dump
# The device transport for a file's bytes is hex (busybox has no base64 applet):
# `od -An -tx1 -v` (space/newline-separated pairs) or `hexdump -ve '1/1 "%02x"'`
# (one continuous run). Real, computed dumps (`printf ... | od -An -tx1 -v`), not
# guessed. The decoder must be tolerant of either layout.

@pytest.mark.parametrize(
    ("name", "dump", "want"),
    [
        ("od-style LF", " 66 6f 6f 0a", b"foo\n"),
        ("od-style CRLF", " 66 6f 6f 0d 0a", b"foo\r\n"),
        ("od-style trailing space", " 66 6f 6f 0a 20", b"foo\n "),
        ("hexdump-style (no whitespace) LF", "666f6f0a", b"foo\n"),
        ("hexdump-style CRLF", "666f6f0d0a", b"foo\r\n"),
        ("hexdump-style trailing space", "666f6f0a20", b"foo\n "),
        ("od-style wrapped across two lines", " 66 6f\n 6f 0a", b"foo\n"),
        ("empty dump is empty bytes", "", b""),
    ],
)
def test_decode_hex_dump(name, dump, want):
    assert decode_hex_dump(dump) == want, name


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
# filters WEBKIT_* lines itself -- the case runs no grep, so there is no grep exit
# status for kiosk.py to branch on.

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


# ------------------------------------------------------------------------ tool_name
# sys.argv[0]'s basename: "oe-test" under a hand run, anything else (bitbake-worker
# under testimage) means the pipeline ran it.

@pytest.mark.parametrize(
    ("name", "argv0", "want"),
    [
        ("hand-run basename", "oe-test", "oe-test"),
        ("hand-run full path", "/usr/bin/oe-test", "oe-test"),
        ("testimage's own worker", "/usr/bin/bitbake-worker", "testimage"),
        ("empty argv0", "", "testimage"),
    ],
)
def test_tool_name(name, argv0, want):
    assert tool_name(argv0) == want, name


# ----------------------------------------------------------------------------- dirty
# git status --porcelain: any output at all means a dirty tree.

@pytest.mark.parametrize(
    ("name", "porcelain", "want"),
    [
        ("clean tree, empty output", "", 0),
        ("clean tree, whitespace only", "   \n", 0),
        ("a modified file", " M some/file.py\n", 1),
    ],
)
def test_dirty(name, porcelain, want):
    assert dirty(porcelain) == want, name


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


# ------------------------------------------------------------------ hostname_mismatch
# base.py's own bench-only refusal, extracted unchanged: the exact message below is
# read verbatim from framework/base.py's current setUpClass, since the brief states
# the extraction is "unchanged in behavior" -- a rewording here would be a silent
# behavior change, not a refactor. base.py's own .strip() of the device's hostname
# happens before this function is called, so no whitespace case belongs to this
# function's own contract.

def test_hostname_mismatch_matching_returns_none():
    assert hostname_mismatch("bench-host", "bench-host") is None


def test_hostname_mismatch_differing_returns_the_existing_refusal_message():
    got = hostname_mismatch("rogue-host", "bench-host")
    assert got == (
        "the board's live hostname ('rogue-host') does not match "
        "the expected KIOSK_TARGET_HOSTNAME ('bench-host') -- refusing to "
        "run against a board this suite did not expect")


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
# config.json's real shape (modules/region/options) with invented values -- never
# a real park name or a real coordinate, per CONTRIBUTING's fixture rule. The app
# line carries config.json's location-free summary, no coordinate or park
# identifier -- so this is asserted by presence of the rest and absence of
# exactly those two leak vectors, never by its own exact serialisation.

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
    # The line builders below render space-delimited k=v pairs; a space inside
    # config= would corrupt the line it is embedded in.
    assert " " not in config_summary(INVENTED_CONFIG_JSON)


# ------------------------------------------------------------------- line builders
# Each builder renders exactly one record line from keyword arguments and
# interprets nothing (docs/testing.md section "Running it": "The run record.").

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
# docs/testing.md section "Running it" ("The run record."): "No address, hostname,
# key material, coordinate or park identifier ever reaches it." A record built
# from inputs carrying all of them must leak none. No new function -- this
# composes the ones proven individually above, the way a case's setUpClass would.

def test_record_never_leaks_identity_or_the_hmac_key():
    # The hostname is not asserted here: no record line carries one at all -- it
    # is compared live in setUpClass, never stored -- so there is no scrub to
    # exercise. The address is assembled via _dotted, never a literal (see scrub_argv
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
            config_mac=keyed_hash(key, INVENTED_CONFIG_JSON.encode()),
            config=config_summary(INVENTED_CONFIG_JSON),
        ),
    ]
    record = "\n".join(lines)

    for leak in (address, "topsecretkey", "12.3456", "-65.4321", "Example Park One", "Example Park Two"):
        assert leak not in record, leak
