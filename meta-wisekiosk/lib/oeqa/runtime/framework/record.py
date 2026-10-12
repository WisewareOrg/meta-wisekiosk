"""Pure parsers and boundary-value helpers shared across the bench config and device tests. Every
function here is pure -- text or bytes in, text or bytes out, no board, no file, no network.
"""
import hashlib
import hmac
import re

_BUILDINFO_LINE = re.compile(r"^meta-wisekiosk\s+=\s+(\S+)", re.MULTILINE)


def parse_buildinfo(text):
    """Extract the layer commit from `/etc/buildinfo`'s own line.

    image-buildinfo writes one line per layer as `"%-17s = %s:%s%s"` (`<layer> = <branch>:<sha>[
    -- modified]`); this reads the `meta-wisekiosk` layer's own line, the same field
    `tools/reproducibility-gate.sh`'s own awk program parses.

    Args:
        text (str): The booted board's `/etc/buildinfo` contents, or any text containing a
            `meta-wisekiosk = ...` line in that shape.

    Returns:
        str: The sha (or `image-buildinfo`'s own `<unknown>` literal) after the last colon on the
        `meta-wisekiosk` line, or `""` if no such line is present.
    """
    m = _BUILDINFO_LINE.search(text.replace("\r", ""))
    if not m:
        return ""
    return m.group(1).rpartition(":")[-1]


def keyed_hash(key, data):
    """Hex HMAC-SHA256 of data under key.

    Args:
        key (bytes): The HMAC key.
        data (bytes): The bytes to hash.

    Returns:
        str: The hex-encoded HMAC-SHA256 digest. Never embeds `key` in its output.
    """
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def decode_hex_dump(dump):
    """Decode a device-transported hex dump into bytes.

    Tolerates either of busybox's own output shapes, since it has no base64 applet and hex is the
    byte-safe transport: `od -An -tx1 -v` (space/newline-separated byte pairs) or `hexdump -ve '1/1
    "%02x"'` (one continuous run, no whitespace at all).

    Args:
        dump (str): The hex dump text, in either layout. Whitespace carries no meaning and is
            stripped before decoding.

    Returns:
        bytes: The decoded bytes.

    Raises:
        ValueError: `dump`, with whitespace stripped, is not a valid hex string.
    """
    return bytes.fromhex(re.sub(r"\s+", "", dump))
