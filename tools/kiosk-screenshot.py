#!/usr/bin/env python3
"""Capture the buffer the kiosk's panel is scanning out, whoever drew it, as a PNG.

    tools/kiosk-screenshot.py root@<host> [out.png]

Exits 0 with a PNG; 1 with a PNG and BLANK if every pixel is the same; any other failure is 1 with the
reason on stderr.

The default output goes under local/: a capture is a picture of the site's live kiosk page, and local/
is gitignored.

Reading it:

    min=0 max=255 mean~4   healthy page -- black background, sparse light text.
                           A mean near zero is NORMAL.
    text console           the browser is not on the panel: not running, still
                           starting, or an operator is on another console.

It is the primary plane handed to the display hardware, so a mouse pointer is not in it. It is not what
reaches the glass: an unplugged panel reads the same. A frame the page replaces mid-copy can mix two.

A capture cannot tell you the render is LIVE, so the device's clock is taken in the same ssh: compare it
with the clock the page renders. An existing file is never overwritten, so a stale PNG cannot pass for a
fresh one.
"""

import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

_SSH = ("ssh", "-oBatchMode=yes", "-oStrictHostKeyChecking=no", "-oUserKnownHostsFile=/dev/null", "-oConnectTimeout=10")
_CAPTURE = "date '+device clock at capture: %H:%M:%S' >&2; kiosk-drmgrab"
_LINEAR = 0
_T_TILED = 0x0700000000000001
# where in a tile its top-left, top-right, bottom-left and bottom-right 1 KB subtiles lie, on even and odd rows of tiles
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
            ValueError: the capture is not in a layout this decodes, or is cut short.
        """
        header, _, self._data = capture.partition(b"\n")
        width, height, pitch, self._format, modifier = header.decode().split()
        self.width, self.height, self._pitch, self._modifier = int(width), int(height), int(pitch), int(modifier)
        if (self._format, self._modifier) not in (("XR24", _T_TILED), ("RG16", _LINEAR)):
            raise ValueError(f"layout not decoded: {self._format} {self._modifier:#x}")
        rows = -(-self.height // 32) * 32 if self._modifier == _T_TILED else self.height
        if len(self._data) < self._pitch * rows:
            raise ValueError(f"cut short: {len(self._data)} of {self._pitch * rows} bytes")

    def rgb(self) -> bytes:
        """Decode the buffer.

        Returns:
            Its pixels, row by row, as 8-bit red, green and blue.
        """
        rgb = bytearray(self.width * self.height * 3)
        if self._modifier == _T_TILED:
            pixels = self._untiled()
            rgb[0::3], rgb[1::3], rgb[2::3] = pixels[2::4], pixels[1::4], pixels[0::4]
        else:
            rows = (self._data[y * self._pitch : y * self._pitch + self.width * 2] for y in range(self.height))
            pixels = struct.unpack(f"<{self.width * self.height}H", b"".join(rows))
            rgb[0::3] = bytes((p >> 11) * 255 // 31 for p in pixels)
            rgb[1::3] = bytes((p >> 5 & 63) * 255 // 63 for p in pixels)
            rgb[2::3] = bytes((p & 31) * 255 // 31 for p in pixels)
        return bytes(rgb)

    def _untiled(self) -> bytes:
        """Lay out a VC4 T-tiled buffer in rows: mesa's `vc4_tiling.c`, for 4 bytes a pixel.

        Returns:
            The rows' bytes.
        """
        across = self._pitch // 128
        rows = bytearray()
        for y in range(self.height):
            odd = y >> 5 & 1
            row = bytearray()
            for x in range(0, self._pitch // 4, 4):
                tile_x = across - 1 - (x >> 5) if odd else x >> 5
                subtile = _SUBTILES[odd][(y >> 4 & 1) << 1 | (x >> 4 & 1)]
                at = 4096 * ((y >> 5) * across + tile_x) + 1024 * subtile
                at += 64 * ((y >> 2 & 3) << 2 | (x >> 2 & 3)) + 16 * (y & 3)
                row += self._data[at : at + 16]
            rows += row[: self.width * 4]
        return bytes(rows)


def png(width: int, height: int, rgb: bytes) -> bytes:
    """Encode pixels.

    Args:
        width: the image's width.
        height: the image's height.
        rgb: its pixels, as `Scanout.rgb` gives them.

    Returns:
        The PNG.
    """
    rows = b"".join(b"\0" + rgb[y * width * 3 : (y + 1) * width * 3] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunks = ((b"IHDR", header), (b"IDAT", zlib.compress(rows)), (b"IEND", b""))
    return b"\x89PNG\r\n\x1a\n" + b"".join(
        struct.pack(">I", len(body)) + name + body + struct.pack(">I", zlib.crc32(name + body)) for name, body in chunks
    )


def main() -> int:
    """Capture the panel of the host named on the command line.

    Returns:
        The exit status.
    """
    if len(sys.argv) < 2:
        sys.exit("usage: kiosk-screenshot.py <ssh-target> [out.png]")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else time.strftime("local/kiosk-%Y%m%d-%H%M%S.png"))
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        sys.exit(f"{out} exists -- refusing to overwrite a capture you may be about to read as fresh")
    capture = subprocess.run([*_SSH, sys.argv[1], _CAPTURE], stdout=subprocess.PIPE)
    if capture.returncode != 0:
        sys.exit("capture failed on the device")
    try:
        scanout = Scanout(capture.stdout)
    except ValueError as error:
        sys.exit(str(error))
    rgb = scanout.rgb()
    out.write_bytes(png(scanout.width, scanout.height, rgb))
    print(f"wrote {out}: {scanout.width}x{scanout.height} min={min(rgb)} max={max(rgb)} mean={sum(rgb) / len(rgb):.1f}")
    if rgb == rgb[:3] * (scanout.width * scanout.height):
        print("BLANK: every pixel identical")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
