"""The boundary value both the accept step and the bench-config precondition compute: a hex
HMAC-SHA256 over bytes decoded from a device-transported hex dump. Every function here is pure --
text or bytes in, text or bytes out, no board, no file, no network.
"""
import hashlib
import hmac
import re


def keyed_hash(key, data):
    """Hex HMAC-SHA256 of data under key. Never embeds key in its output."""
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def decode_hex_dump(dump):
    """Bytes from a device-transported hex dump -- `od -An -tx1 -v`
    (space/newline-separated pairs) or `hexdump -ve '1/1 "%02x"'` (one
    continuous run), either layout tolerated: busybox has no base64 applet,
    so hex is the byte-safe transport, and whitespace carries no meaning."""
    return bytes.fromhex(re.sub(r"\s+", "", dump))
