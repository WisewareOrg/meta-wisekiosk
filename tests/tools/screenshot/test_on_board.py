"""Screenshot suite: on the board, `just screenshot` reads the page, the console and a blank console.

It leaves the page on the panel:

    bench test <ref> -- tests/tools/screenshot -rP
"""

import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from board import Board
from board.app.inspector import NoPageError
from board.part import invalid_if
from picture import pixels

# the first read in this page load starts painting every pixel of the page a colour that names its
# place, which can outlast one read; the size painted, once it is
_PAINT = """(() => {
    const paint = () => {
        const c = document.createElement("canvas"), w = c.width = innerWidth, h = c.height = innerHeight;
        c.style.cssText = `position:fixed;left:0;top:0;width:${w}px;height:${h}px;z-index:2147483647`;
        const x = c.getContext("2d"), d = x.createImageData(w, h);
        for (let i = 0, p = 0; i < h; i++)
            for (let j = 0; j < w; j++) {
                d.data[p++] = j & 255; d.data[p++] = i & 255; d.data[p++] = (j >> 8) << 4 | i >> 8; d.data[p++] = 255;
            }
        x.putImageData(d, 0, 0);
        document.body.append(c);
        window.painted = `${w}x${h}`;
    };
    if (!window.painting) window.painting = setTimeout(paint);
    return window.painted;
})()"""
_SETTLE_SECONDS = 3
_SCREENSHOT_TIMEOUT_SECONDS = 60
# the text keeps the red console from being a flat frame, which the tool calls blank
_RED = "printf '\\033[41m\\033[2Jconsole' > /dev/tty2"
_BLACK = "printf '\\033[?25l\\033[40m\\033[2J' > /dev/tty2"


def test_reads_what_the_panel_shows(board: Board, record_property: Callable[[str, object], None]) -> None:
    """The PNG holds the painted page pixel for pixel, then the console's colour, and a blank console is called blank.

    Args:
        board: the board under test.
        record_property: records how many pixels were wrong and how many were red.
    """
    board.app.install_probe()
    board.app.wait_until_on_panel()
    painted = board.wait_for(lambda: _painted(board))
    time.sleep(_SETTLE_SECONDS)

    page, png = _screenshot(board)

    width, height, drawn = pixels(png)
    expected = ((x & 255, y & 255, (x >> 8) << 4 | y >> 8) for y in range(height) for x in range(width))
    wrong = sum(pixel != colour for pixel, colour in zip(drawn, expected, strict=True))
    record_property("wrong_pixels", wrong)
    assert page.returncode == 0, f"the tool returned {page.returncode}: {page.stderr}"
    assert (width, height) == board.screen.mode(), f"the picture is {width}x{height}, not the panel's mode"
    assert painted == f"{width}x{height}", f"{painted} was painted, and the picture is {width}x{height}"
    assert wrong == 0, f"{wrong} of {len(drawn)} pixels are not the ones painted there"

    board.cleanup.callback(board.run, "chvt 1", check=True)
    board.run("chvt 2", check=True)
    board.seconds_until(lambda: [plane.allocated_by for plane in board.screen.planes()] == ["fbcon"])
    board.run(_RED, check=True)
    time.sleep(_SETTLE_SECONDS)

    console, png = _screenshot(board)

    _, _, drawn = pixels(png)
    red = sum(r > 150 and g < 20 and b < 20 for r, g, b in drawn)
    record_property("red_pixels", red)
    assert console.returncode == 0, f"the tool returned {console.returncode}: {console.stderr}"
    assert red > 0.95 * len(drawn), f"{red} of {len(drawn)} pixels are the console's red"

    board.run(_BLACK, check=True)
    time.sleep(_SETTLE_SECONDS)

    blank, _ = _screenshot(board)

    assert blank.returncode != 0, "a blank console returned 0"
    assert "BLANK" in blank.stdout, f"a blank console was not called blank: {blank.stdout}"


def _painted(board: Board) -> object:
    """Start painting the page, once in each page load, and read the size painted.

    Args:
        board: the board under test.

    Returns:
        The size, as `<width>x<height>`; None if it is not painted yet, or there is no page to paint.
    """
    try:
        return board.app.inspector.evaluate(_PAINT)
    except NoPageError:
        return None


def _screenshot(board: Board) -> tuple[subprocess.CompletedProcess[str], bytes]:
    """Take a picture of the panel with `just screenshot`; the check is invalid if it took none.

    Args:
        board: the board under test.

    Returns:
        The finished command, which returns 1 for a blank panel, and the PNG.
    """
    with tempfile.TemporaryDirectory() as directory:
        png = Path(directory) / "panel.png"
        command = subprocess.run(
            ["just", "screenshot", board.host.rpartition("@")[2], png],
            capture_output=True,
            text=True,
            timeout=_SCREENSHOT_TIMEOUT_SECONDS,
        )
        with invalid_if("the tool took no picture of the panel"):
            assert png.exists(), command.stderr
        return command, png.read_bytes()
