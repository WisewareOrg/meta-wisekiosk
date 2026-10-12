"""Pure parsers and boundary-value helpers shared across the bench config and device tests. Every
function here is pure -- text or bytes in, text or bytes out, no board, no file, no network.
"""
import hashlib
import hmac
import re

_BUILDINFO_LINE = re.compile(r"^meta-wisekiosk\s+=\s+(\S+)", re.MULTILINE)


def parse_buildinfo(text):
    """The sha from /etc/buildinfo's "meta-wisekiosk = <branch>:<sha>[ -- modified]"
    line (image-buildinfo writes "%-17s = %s:%s%s" per BBLAYERS entry), or "" if no such line."""
    m = _BUILDINFO_LINE.search(text.replace("\r", ""))
    if not m:
        return ""
    return m.group(1).rpartition(":")[-1]


def keyed_hash(key, data):
    """Hex HMAC-SHA256 of data under key. Never embeds key in its output."""
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def decode_hex_dump(dump):
    """Bytes from a device-transported hex dump -- `od -An -tx1 -v`
    (space/newline-separated pairs) or `hexdump -ve '1/1 "%02x"'` (one
    continuous run), either layout tolerated: busybox has no base64 applet,
    so hex is the byte-safe transport, and whitespace carries no meaning."""
    return bytes.fromhex(re.sub(r"\s+", "", dump))
