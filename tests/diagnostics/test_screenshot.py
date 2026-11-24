"""Diagnostics: `just screenshot` reads what the panel shows, for the page, the console and a blank console.

Outside the regression suite: it checks an operator's tool, tied to no TST, so its on-board run is its
test. It leaves the page on the panel:

    bench test <ref> -- tests/diagnostics -k screenshot -rP
"""

import subprocess
import time
import zlib
from pathlib import Path

from board import Board

# paints every pixel of the page the colour `_pattern` gives its place
_PAINT = """(() => {
    const c = document.createElement("canvas"), w = c.width = innerWidth, h = c.height = innerHeight;
    c.style.cssText = `position:fixed;left:0;top:0;width:${w}px;height:${h}px;z-index:2147483647`;
    const x = c.getContext("2d"), d = x.createImageData(w, h);
    for (let i = 0, p = 0; i < h; i++)
        for (let j = 0; j < w; j++) {
            d.data[p++] = j & 255; d.data[p++] = i & 255; d.data[p++] = (j >> 8) << 4 | i >> 8; d.data[p++] = 255;
        }
    x.putImageData(d, 0, 0);
    document.body.append(c);
    return `${w}x${h}`;
})()"""
_SETTLE_SECONDS = 3
# the text keeps the red console from being a flat frame, which the tool calls blank
_RED = "printf '\\033[41m\\033[2Jconsole' > /dev/tty2"
_BLACK = "printf '\\033[?25l\\033[40m\\033[2J' > /dev/tty2"


def _pattern(x: int, y: int) -> tuple[int, int, int]:
    """The colour painted at one place.

    Args:
        x: its column.
        y: its row.

    Returns:
        Red, green and blue.
    """
    return x & 255, y & 255, (x >> 8) << 4 | y >> 8


def _pixels(png: Path) -> tuple[int, int, list[tuple[int, int, int]]]:
    """Read a PNG as `scanout-png.py` writes it.

    Args:
        png: the file.

    Returns:
        Its width, height, and pixels row by row.
    """
    data = png.read_bytes()
    width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    at = data.index(b"IDAT")
    rows = zlib.decompress(data[at + 4 : at + 4 + int.from_bytes(data[at - 4 : at], "big")])
    stride = width * 3 + 1
    rgb = b"".join(rows[y * stride + 1 : (y + 1) * stride] for y in range(height))
    return width, height, list(zip(rgb[0::3], rgb[1::3], rgb[2::3], strict=True))


def _screenshot(board: Board, out: Path) -> subprocess.CompletedProcess[str]:
    """Run `just screenshot`, and print what it printed.

    Args:
        board: the board under test.
        out: where it writes the PNG.

    Returns:
        The finished command.
    """
    command = subprocess.run(
        ["just", "screenshot", board.host.rpartition("@")[2], str(out)], capture_output=True, text=True
    )
    print(command.stdout, command.stderr)
    return command


def _shown_by(board: Board) -> list[str]:
    """Read whose buffers the panel shows.

    Args:
        board: the board under test.

    Returns:
        What allocated each.
    """
    return [plane.allocated_by for plane in board.screen.planes()]


def test_screenshot(board: Board, tmp_path: Path) -> None:
    """The PNG holds the painted page pixel for pixel, then the console's colour, then a blank console.

    Args:
        board: the board under test.
        tmp_path: where the PNGs are written.
    """
    board.app.install_probe()
    board.app.wait_until_on_panel()
    painted = board.app.inspector.evaluate(_PAINT)
    time.sleep(_SETTLE_SECONDS)

    page = _screenshot(board, tmp_path / "page.png")

    assert page.returncode == 0, "no screenshot of the page"
    width, height, pixels = _pixels(tmp_path / "page.png")
    assert (width, height) == board.screen.mode() and painted == f"{width}x{height}", f"{width}x{height}, {painted}"
    wrong = sum(pixel != _pattern(i % width, i // width) for i, pixel in enumerate(pixels))
    assert wrong == 0, f"{wrong} of {len(pixels)} pixels are not the ones painted there"

    board.cleanup.callback(board.seconds_until, lambda: _shown_by(board) == ["kiosk-browser"])
    board.cleanup.callback(board.run, "systemctl kill -s KILL getty@tty2.service; chvt 1", check=True)
    board.run("chvt 2", check=True)
    board.seconds_until(lambda: _shown_by(board) == ["fbcon"])
    board.run(_RED, check=True)
    time.sleep(_SETTLE_SECONDS)

    console = _screenshot(board, tmp_path / "console.png")

    assert console.returncode == 0, "no screenshot of the console"
    _, _, pixels = _pixels(tmp_path / "console.png")
    red = sum(r > 150 and g < 20 and b < 20 for r, g, b in pixels)
    assert red > 0.95 * len(pixels), f"{red} of {len(pixels)} pixels are the console's red"

    board.run(_BLACK, check=True)
    time.sleep(_SETTLE_SECONDS)

    blank = _screenshot(board, tmp_path / "blank.png")

    assert blank.returncode != 0 and "BLANK" in blank.stdout, "a blank console was not called blank"
    assert (tmp_path / "blank.png").exists(), "no screenshot of the blank console"
