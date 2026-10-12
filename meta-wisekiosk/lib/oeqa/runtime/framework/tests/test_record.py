"""Specifies oeqa/runtime/framework/record.py: parse_buildinfo (the provenance test's own parser),
keyed_hash and decode_hex_dump (the two functions tools/pipeline/config-mac.py calls to agree with
the board's own accept step on a boundary value by construction, not by copy).

Every case is a constructed string or bytes value -- no board, no subprocess, no network.
"""

import hashlib
import hmac
import re
import subprocess
from pathlib import Path

import pytest

from framework.record import decode_hex_dump, keyed_hash, parse_buildinfo

# --------------------------------------------------------------- parse_buildinfo
# image-buildinfo writes one line per layer as "%-17s = %s:%s%s"; ported from
# tools/reproducibility-gate.sh's own awk/sed.

SHA = "deadbeef" * 5  # 40 hex chars, the shape image-buildinfo and git both require

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


# ------------------------------------------------------------------------- keyed_hash
# RFC 4231 test case 1 (HMAC-SHA256), a known-answer vector independent of this tree, plus an
# independent computation of a second vector via hmac/hashlib directly (not the module under
# test) so the expectation is never derived from the implementation it checks.

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
