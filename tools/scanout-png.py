#!/usr/bin/env python3
"""Decode a scanout buffer, as kiosk-drmgrab writes it, into a PNG.

    scanout-png.py <capture> <out.png>

Prints the image's size and its least, greatest and mean channel value. Exits 1 if every pixel is the
same, with the PNG written; exits 1 and writes nothing if it cannot decode the capture.
"""

import struct
import sys
import zlib
from pathlib import Path

_LINEAR = 0
_T_TILED = 0x0700000000000001
# the order a tile's four 1 KB subtiles lie in, on even and odd rows of tiles
_SUBTILES = ((0, 3, 1, 2), (2, 1, 3, 0))


class Scanout:
    """A buffer the panel scanned out.

    Attributes:
        width: its width, in pixels.
        height: its height, in pixels.
    """

    width: int
    height: int

    def __init__(self, capture: bytes) -> None:
        """Read a capture.

        Args:
            capture: what kiosk-drmgrab wrote.

        Raises:
            ValueError: the capture is not in a layout this decodes.
        """
        header, _, self._data = capture.partition(b"\n")
        width, height, pitch, self._format, modifier = header.decode().split()
        self.width, self.height, self._pitch, self._modifier = int(width), int(height), int(pitch), int(modifier)
        if self._modifier not in (_LINEAR, _T_TILED) or (self._format, self._modifier) == ("RG16", _T_TILED):
            raise ValueError(f"layout not decoded: {self._format} {self._modifier:#x}")
        if self._format not in ("XR24", "RG16"):
            raise ValueError(f"format not decoded: {self._format}")

    def rgb(self) -> bytes:
        """Decode the buffer.

        Returns:
            Its pixels, row by row, as 8-bit red, green and blue.
        """
        rows = self._tiled_rows() if self._modifier == _T_TILED else self._linear_rows()
        return b"".join(self._rgb_row(row) for row in rows)

    def _linear_rows(self) -> list[bytes]:
        """Split a linear buffer.

        Returns:
            Each row's bytes.
        """
        used = self.width * (2 if self._format == "RG16" else 4)
        return [self._data[y * self._pitch : y * self._pitch + used] for y in range(self.height)]

    def _tiled_rows(self) -> list[bytes]:
        """Lay out a VC4 T-tiled buffer in rows: mesa's `vc4_tiling.c`, for 4 bytes a pixel.

        Returns:
            Each row's bytes.
        """
        across = self._pitch // 128
        rows = []
        for y in range(self.height):
            odd = y >> 5 & 1
            row = bytearray()
            for x in range(0, self._pitch // 4, 4):
                tile_x = across - 1 - (x >> 5) if odd else x >> 5
                subtile = _SUBTILES[odd][(y >> 4 & 1) << 1 | (x >> 4 & 1)]
                at = 4096 * ((y >> 5) * across + tile_x) + 1024 * subtile
                at += 64 * ((y >> 2 & 3) << 2 | (x >> 2 & 3)) + 16 * (y & 3)
                row += self._data[at : at + 16]
            rows.append(bytes(row[: self.width * 4]))
        return rows

    def _rgb_row(self, row: bytes) -> bytes:
        """Reorder a row's pixels.

        Args:
            row: the row's bytes.

        Returns:
            Red, green and blue bytes.
        """
        rgb = bytearray(self.width * 3)
        if self._format == "RG16":
            pixels = struct.unpack(f"<{self.width}H", row)
            rgb[0::3] = bytes((p >> 11) * 255 // 31 for p in pixels)
            rgb[1::3] = bytes((p >> 5 & 63) * 255 // 63 for p in pixels)
            rgb[2::3] = bytes((p & 31) * 255 // 31 for p in pixels)
        else:
            rgb[0::3], rgb[1::3], rgb[2::3] = row[2::4], row[1::4], row[0::4]
        return bytes(rgb)


def png(width: int, height: int, rgb: bytes) -> bytes:
    """Encode pixels.

    Args:
        width: the image's width.
        height: the image's height.
        rgb: its pixels, as `Scanout.rgb` gives them.

    Returns:
        The PNG.
    """

    def chunk(name: bytes, body: bytes) -> bytes:
        """Frame one chunk.

        Args:
            name: its name.
            body: its contents.

        Returns:
            The chunk.
        """
        return struct.pack(">I", len(body)) + name + body + struct.pack(">I", zlib.crc32(name + body))

    rows = b"".join(b"\0" + rgb[y * width * 3 : (y + 1) * width * 3] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def main() -> int:
    """Decode the capture named on the command line.

    Returns:
        The exit status.
    """
    capture, out = Path(sys.argv[1]), Path(sys.argv[2])
    scanout = Scanout(capture.read_bytes())
    rgb = scanout.rgb()
    out.write_bytes(png(scanout.width, scanout.height, rgb))
    print(f"wrote {out}: {scanout.width}x{scanout.height} min={min(rgb)} max={max(rgb)} mean={sum(rgb) / len(rgb):.1f}")
    if rgb == rgb[:3] * (scanout.width * scanout.height):
        print("BLANK: every pixel identical")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
