"""Reading the screenshot tool's pictures without the tool's own code."""

import struct
import zlib


def pixels(png: bytes) -> tuple[int, int, list[tuple[int, int, int]]]:
    """Read a PNG of 8-bit red, green and blue whose rows are unfiltered, as the tool writes it.

    Args:
        png: the file's bytes.

    Returns:
        Its width, height, and pixels row by row.
    """
    assert png[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {png[:8]}"
    chunks = {}
    at = 8
    while at < len(png):
        end = at + 8 + int.from_bytes(png[at : at + 4])
        assert zlib.crc32(png[at + 4 : end]) == int.from_bytes(png[end : end + 4]), f"a chunk's checksum at {at}"
        chunks[png[at + 4 : at + 8]] = png[at + 8 : end]
        at = end + 4
    width, height, *form = struct.unpack(">IIBBBBB", chunks[b"IHDR"])
    assert form == [8, 2, 0, 0, 0], f"not 8-bit red, green and blue: {form}"
    rows = zlib.decompress(chunks[b"IDAT"])
    stride = width * 3 + 1
    assert len(rows) == stride * height, f"{len(rows)} bytes of rows for {width}x{height}"
    assert not any(rows[::stride]), "a row is filtered"
    rgb = b"".join(rows[y * stride + 1 : (y + 1) * stride] for y in range(height))
    return width, height, list(zip(rgb[0::3], rgb[1::3], rgb[2::3], strict=True))
