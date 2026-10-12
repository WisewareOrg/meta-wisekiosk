"""Specifies oeqa/runtime/framework/record.py: keyed_hash and decode_hex_dump, the two functions
tools/pipeline/config-mac.py calls to agree with the board's own accept step on a boundary value
by construction, not by copy.

Every case is a constructed string or bytes value -- no board, no subprocess, no network.
"""

import hashlib
import hmac

import pytest

from framework.record import decode_hex_dump, keyed_hash

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
