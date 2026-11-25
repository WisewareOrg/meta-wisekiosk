"""Target suite: `just screenshot` reads what the panel shows, for the page, the console and a blank console."""

import time
import zlib

from board_test import BoardTest

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
# the text keeps the red console from being a flat frame, which the tool calls blank
_RED = "printf '\\033[41m\\033[2Jconsole' > /dev/tty2"
_BLACK = "printf '\\033[?25l\\033[40m\\033[2J' > /dev/tty2"


def _pixels(png: bytes) -> tuple[int, int, list[tuple[int, int, int]]]:
    """Read a PNG as `kiosk-screenshot.py` writes it.

    Args:
        png: the file's bytes.

    Returns:
        Its width, height, and pixels row by row.
    """
    width, height = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    at = png.index(b"IDAT")
    rows = zlib.decompress(png[at + 4 : at + 4 + int.from_bytes(png[at - 4 : at], "big")])
    stride = width * 3 + 1
    rgb = b"".join(rows[y * stride + 1 : (y + 1) * stride] for y in range(height))
    return width, height, list(zip(rgb[0::3], rgb[1::3], rgb[2::3], strict=True))


class TestScreenshot(BoardTest):
    """`just screenshot` reads what the panel shows."""

    def test_page(self) -> None:
        """The PNG holds the painted page, pixel for pixel."""
        self.board.app.turn_the_inspector_on()
        self.board.app.wait_until_on_panel()
        painted = self.board.wait_for(lambda: self.board.app.inspector.evaluate(_PAINT))
        time.sleep(_SETTLE_SECONDS)

        page, png = self.board.screen.screenshot()

        width, height, pixels = _pixels(png)
        expected = ((x & 255, y & 255, (x >> 8) << 4 | y >> 8) for y in range(height) for x in range(width))
        wrong = sum(pixel != colour for pixel, colour in zip(pixels, expected, strict=True))
        self.record(wrong_pixels=wrong)
        assert page.returncode == 0, f"the tool returned {page.returncode}: {page.stderr}"
        assert (width, height) == self.board.screen.mode(), f"the picture is {width}x{height}, not the panel's mode"
        assert painted == f"{width}x{height}", f"{painted} was painted, and the picture is {width}x{height}"
        assert wrong == 0, f"{wrong} of {len(pixels)} pixels are not the ones painted there"

    def test_console(self) -> None:
        """The PNG holds the console's colour, and a blank console is called blank."""
        self.board.seconds_until(lambda: self.board.screen.shown_by() == ["kiosk-browser"])
        self.board.cleanup.callback(self.board.run, "chvt 1", check=True)
        self.board.run("chvt 2", check=True)
        self.board.seconds_until(lambda: self.board.screen.shown_by() == ["fbcon"])
        self.board.run(_RED, check=True)
        time.sleep(_SETTLE_SECONDS)

        console, png = self.board.screen.screenshot()

        _, _, pixels = _pixels(png)
        red = sum(r > 150 and g < 20 and b < 20 for r, g, b in pixels)
        self.record(red_pixels=red)
        assert console.returncode == 0, f"the tool returned {console.returncode}: {console.stderr}"
        assert red > 0.95 * len(pixels), f"{red} of {len(pixels)} pixels are the console's red"

        self.board.run(_BLACK, check=True)
        time.sleep(_SETTLE_SECONDS)
        blank, _ = self.board.screen.screenshot()

        assert blank.returncode != 0, "a blank console returned 0"
        assert "BLANK" in blank.stdout, f"a blank console was not called blank: {blank.stdout}"
