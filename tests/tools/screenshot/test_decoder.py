"""Screenshot suite: the tool turns a constructed buffer into the picture it holds, or refuses it.

Host only, on the standard library, so that `just guards` and CI run it as a script. Each test runs the
tool itself, with a stand-in `ssh` that runs the capture command on this host and a stand-in
`kiosk-drmgrab` that writes the buffer. The buffers and their pixels are worked out here, without the
tool's decoder.
"""

import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import NamedTuple

from picture import pixels

_TOOL = Path(__file__).resolve().parents[3] / "tools" / "kiosk-screenshot.py"
_SSH = 'for command; do :; done; exec sh -c "$command"'
_SEND_CAPTURE = 'cat "${0%/*}/capture"'
_NO_BUFFER = "echo 'kiosk-drmgrab: the panel is driven at no mode, or shows no buffer' >&2; exit 1"
# where a tile's four subtiles lie in it, as (x, y), in memory order: drm_fourcc.h, which counts rows from the bottom
_EVEN_ROW = ((0, 0), (0, 1), (1, 1), (1, 0))
_ODD_ROW = ((1, 1), (1, 0), (0, 0), (0, 1))


def _t_tiled(across: int, down: int) -> bytes:
    """Draw each pixel of 32x32 tiles as (its column, its row, 200), in the order the pixels lie in memory.

    Args:
        across: how many tiles wide the buffer is.
        down: how many tiles high it is.

    Returns:
        The buffer, each pixel as blue, green, red and an unused byte.
    """
    buffer = bytearray()
    for row in range(down):
        odd = row % 2
        for column in reversed(range(across)) if odd else range(across):
            for right, low in _ODD_ROW if odd else _EVEN_ROW:
                for at in range(256):
                    x = column * 32 + right * 16 + at // 16 % 4 * 4 + at % 4
                    y = row * 32 + low * 16 + at // 64 * 4 + at // 4 % 4
                    buffer += bytes((200, y, x, 0xAA))
    return bytes(buffer)


# captures as kiosk-drmgrab sends them: a header line, whose last field is the layout, then the buffer
# 50x50 of 64x64, so that the buffer is wider than the picture and the picture spans an even and an odd row of tiles
_TILED = b"50 50 256 XR24 504403158265495553\n" + _t_tiled(2, 2)
# 3x2 with 2 bytes past the end of each row: red, green, blue; white, black, 1 in each channel
_RG16 = b"3 2 8 RG16 0\n" + struct.pack("<8H", 0xF800, 0x07E0, 0x001F, 0xEEEE, 0xFFFF, 0x0000, 0x0821, 0xEEEE)


class Shot(NamedTuple):
    """One run of the tool.

    Attributes:
        status: its exit status.
        stdout: what it printed.
        reason: what reached stderr, without the device's clock.
        png: the picture's bytes; None if there is no picture.
    """

    status: int
    stdout: str
    reason: str
    png: bytes | None


class TestDecoder(unittest.TestCase):
    """The tool turns a constructed buffer into the picture it holds, or refuses it."""

    def setUp(self) -> None:
        """Make a directory holding the stand-in `ssh` and, until a test replaces it, a reader that sends."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.panel = self.directory / "panel.png"
        self._install("ssh", _SSH)
        self._install("kiosk-drmgrab", _SEND_CAPTURE)

    def test_tiled_page(self) -> None:
        """A tiled XR24 buffer gives its pixels."""
        shot = self._shoot(_TILED)

        self.assertEqual(shot.status, 0, shot)
        width, height, drawn = pixels(shot.png)
        self.assertEqual((width, height), (50, 50), "the picture's size")
        wrong = sum(drawn[y * 50 + x] != (x, y, 200) for y in range(50) for x in range(50))
        self.assertEqual(wrong, 0, f"{wrong} of 2500 pixels are not the ones in the buffer")

    def test_linear_console(self) -> None:
        """A linear RG16 buffer gives its pixels, widened to 8 bits."""
        shot = self._shoot(_RG16)

        self.assertEqual(shot.status, 0, shot)
        width, height, drawn = pixels(shot.png)
        self.assertEqual((width, height), (3, 2), "the picture's size")
        self.assertEqual(drawn, [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (0, 0, 0), (8, 4, 8)])

    def test_blank(self) -> None:
        """One colour over the whole panel, which need not be black, gives the picture and is called blank."""
        shot = self._shoot(b"3 2 8 RG16 0\n" + struct.pack("<H", 0xF800) * 8)

        self.assertEqual(shot.status, 1, shot)
        self.assertIn("BLANK", shot.stdout)
        self.assertEqual(pixels(shot.png), (3, 2, [(255, 0, 0)] * 6))

    def test_refuses_linear_xr24(self) -> None:
        """A layout it does not decode is refused by name."""
        shot = self._shoot(b"2 1 8 XR24 0\n" + bytes(8))

        self._assert_refused(shot, "layout not decoded: XR24 0x0")

    def test_refuses_malformed_header(self) -> None:
        """A header without its modifier is refused."""
        shot = self._shoot(b"50 50 256 XR24\n" + bytes(16384))

        self._assert_refused(shot)

    def test_refuses_truncated_tiled(self) -> None:
        """A tiled buffer one byte short is refused."""
        shot = self._shoot(_TILED[:-1])

        self._assert_refused(shot, "cut short")

    def test_refuses_truncated_linear(self) -> None:
        """A linear buffer one byte short is refused."""
        shot = self._shoot(_RG16[:-1])

        self._assert_refused(shot, "cut short")

    def test_refuses_to_overwrite(self) -> None:
        """A file already there is left as it was."""
        self.panel.write_bytes(b"an earlier capture")

        shot = self._shoot(_TILED)

        self._assert_refused(shot, "refusing to overwrite", png=b"an earlier capture")

    def test_no_host_named(self) -> None:
        """Without a host it gives its usage."""
        shot = self._run_tool()

        self._assert_refused(shot, "usage:")

    def test_no_buffer(self) -> None:
        """A panel showing no buffer is refused with the reader's own reason."""
        self._install("kiosk-drmgrab", _NO_BUFFER)

        shot = self._shoot(b"")

        self._assert_refused(shot, "shows no buffer")

    def test_no_reader(self) -> None:
        """A device without the reader is refused with the device shell's reason."""
        (self.directory / "kiosk-drmgrab").unlink()

        shot = self._shoot(b"")

        self._assert_refused(shot, "kiosk-drmgrab: ")
        self.assertIn("capture failed on the device", shot.reason)

    def _install(self, name: str, body: str) -> None:
        """Put a stand-in command on the tool's PATH.

        Args:
            name: the command.
            body: its shell script.
        """
        command = self.directory / name
        command.write_text(f"#!/bin/sh\n{body}\n")
        command.chmod(0o755)

    def _shoot(self, capture: bytes) -> Shot:
        """Run the tool for a device whose reader sends `capture`.

        Args:
            capture: what the reader sends.

        Returns:
            The run.
        """
        (self.directory / "capture").write_bytes(capture)
        return self._run_tool("root@kiosk", self.panel.name)

    def _run_tool(self, *arguments: str) -> Shot:
        """Run the tool.

        Args:
            *arguments: its arguments.

        Returns:
            The run.
        """
        run = subprocess.run(
            [sys.executable, _TOOL, *arguments],
            cwd=self.directory,
            env={**os.environ, "PATH": f"{self.directory}:{os.environ['PATH']}"},
            capture_output=True,
            text=True,
        )
        reason = "\n".join(line for line in run.stderr.splitlines() if not line.startswith("device clock"))
        return Shot(run.returncode, run.stdout, reason, self.panel.read_bytes() if self.panel.exists() else None)

    def _assert_refused(self, shot: Shot, reason: str = "", png: bytes | None = None) -> None:
        """Assert that the tool failed, said why, and wrote no picture.

        Args:
            shot: the run.
            reason: what the reason must hold.
            png: the picture that was there before.
        """
        self.assertEqual(shot.status, 1, shot)
        self.assertNotEqual(shot.reason, "", "nothing on stderr says why")
        self.assertIn(reason, shot.reason)
        self.assertEqual(shot.png, png, "the picture")


if __name__ == "__main__":
    unittest.main()
