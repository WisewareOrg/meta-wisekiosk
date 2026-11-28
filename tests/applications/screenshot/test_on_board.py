"""Screenshot suite: on the board, `just screenshot` reads the page, the console and a blank console.

It leaves the page on the panel. docs/testing.md has the command that runs it.
"""

import subprocess
import tempfile
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

import pytest
from board import Board
from board.app.inspector import NoPageError
from board.part import invalid_if
from picture import pixels

# starts painting every pixel of the page a colour that names its place, once in each page load, and gives
# the size painted once that is done, which can outlast one read
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
# getty@.service's Restart=always brings back a fresh prompt
_RESET = "printf '\\033c' > /dev/tty2; systemctl kill -s KILL getty@tty2.service"


class TestOnBoard:
    """On the board, `just screenshot` reads what the panel shows.

    Attributes:
        board: the board under test.
        record: records a measured value by name.
    """

    board: Board
    record: Callable[[str, object], None]

    @pytest.fixture(autouse=True)
    def _board_and_record(self, board: Board, record_property: Callable[[str, object], None]) -> None:
        """Put the board and the record on the instance.

        Args:
            board: the board under test.
            record_property: records a measured value by name.
        """
        self.board = board
        self.record = record_property

    def test_reads_what_the_panel_shows(self) -> None:
        """The PNG holds the painted page pixel for pixel, then a red console, and a blank console is called blank."""
        self.board.cleanup.callback(self.board.seconds_until, partial(self._is_shown, "kiosk-browser"))
        self.board.app.turn_the_inspector_on()
        self.board.app.wait_until_on_panel()
        with invalid_if("the page was not painted"):
            painted = self.board.wait_for(self._paint)
        time.sleep(_SETTLE_SECONDS)

        page, png = self._screenshot()
        with invalid_if("the page reloaded before its picture was taken"):
            assert self._paint() == painted

        assert page.returncode == 0, f"the tool returned {page.returncode}: {page.stderr}"
        width, height, drawn = pixels(png)
        expected = ((x & 255, y & 255, (x >> 8) << 4 | y >> 8) for y in range(height) for x in range(width))
        wrong = sum(pixel != colour for pixel, colour in zip(drawn, expected, strict=True))
        self.record("wrong_pixels", wrong)
        assert (width, height) == self.board.screen.mode(), f"the picture is {width}x{height}, not the panel's mode"
        assert painted == f"{width}x{height}", f"{painted} was painted, and the picture is {width}x{height}"
        assert wrong == 0, f"{wrong} of {len(drawn)} pixels are not the ones painted there"

        self.board.cleanup.callback(self.board.run, _RESET)
        self.board.cleanup.callback(self.board.run, "chvt 1", check=True)
        self.board.run("chvt 2", check=True)
        with invalid_if("the console did not reach the panel"):
            self.board.seconds_until(partial(self._is_shown, "fbcon"))
        self.board.run(_RED, check=True)
        time.sleep(_SETTLE_SECONDS)

        console, png = self._screenshot()

        assert console.returncode == 0, f"the tool returned {console.returncode}: {console.stderr}"
        _, _, drawn = pixels(png)
        red = sum(r > 150 and g < 20 and b < 20 for r, g, b in drawn)
        self.record("red_pixels", red)
        assert red > 0.95 * len(drawn), f"{red} of {len(drawn)} pixels are the console's red"

        self.board.run(_BLACK, check=True)
        time.sleep(_SETTLE_SECONDS)

        blank, png = self._screenshot()

        assert blank.returncode == 1, f"the tool returned {blank.returncode} for a blank console: {blank.stderr}"
        assert "BLANK" in blank.stdout, f"a blank console was not called blank: {blank.stdout}{blank.stderr}"
        _, _, drawn = pixels(png)
        lit = sum(pixel != (0, 0, 0) for pixel in drawn)
        assert lit == 0, f"{lit} of {len(drawn)} pixels of a blank console are not black"

    def _paint(self) -> object:
        """Start painting the page, once in each page load.

        Returns:
            The size painted, as `<width>x<height>`; None if it is not painted yet, or there is no page to paint.
        """
        try:
            return self.board.app.inspector.evaluate(_PAINT)
        except NoPageError:
            return None

    def _is_shown(self, program: str) -> bool:
        """Whether the panel shows one program's buffer and no other.

        Args:
            program: the program.

        Returns:
            True if it does.
        """
        return self.board.screen.shown_by() == [program]

    def _screenshot(self) -> tuple[subprocess.CompletedProcess[str], bytes]:
        """Run `just screenshot`.

        Returns:
            The finished command, and the PNG; empty if the tool wrote none.
        """
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "panel.png"
            command = subprocess.run(
                ["just", "screenshot", self.board.host, png],
                capture_output=True,
                text=True,
                timeout=_SCREENSHOT_TIMEOUT_SECONDS,
            )
            return command, png.read_bytes() if png.exists() else b""
