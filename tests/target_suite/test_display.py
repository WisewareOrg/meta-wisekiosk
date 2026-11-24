"""Target suite: the panel shows nothing but the instance, at the minimum resolution."""

from board.screen import Plane
from board_test import BoardTest

# TST031's floor
MIN_WIDTH, MIN_HEIGHT = 1280, 720


class TestDisplay(BoardTest):
    """The panel shows only the instance, with no pointer, at the minimum resolution."""

    def setup_method(self) -> None:
        """Turn on the browser's inspector, and wait for the instance on the panel."""
        self.board.app.turn_the_inspector_on()
        self.board.app.wait_until_on_panel()

    def test_no_pointer_on_the_panel(self) -> None:
        """TST013: with a mouse attached and moved, the panel shows no pointer."""
        self.record(requirement="TST013")

        mouse_at = self.board.mouse.move_over_the_page()
        planes = self.board.screen.planes()

        self.record(mouse_at=mouse_at, planes=str(planes))
        assert len(planes) == 1, f"with the mouse at {mouse_at}, the panel shows {planes}"

    def test_instance_covers_the_panel(self) -> None:
        """TST030: the screen shows the browser over the whole panel, and nothing else."""
        self.record(requirement="TST030")

        planes = self.board.screen.planes()
        width, height = self.board.screen.mode()

        self.record(planes=str(planes), display_mode=f"{width}x{height}")
        assert planes == [Plane("kiosk-browser", f"{width}x{height}+0+0")], f"the screen shows {planes}"

    def test_minimum_resolution(self) -> None:
        """TST031: the display mode the panel is driven at, and the page's layout size, are each at least 1280x720."""
        self.record(requirement="TST031")

        width, height = self.board.screen.mode()
        page_width, page_height = self.board.app.layout_size()

        self.record(display_mode=f"{width}x{height}", layout_size=f"{page_width}x{page_height}")
        assert width >= MIN_WIDTH and height >= MIN_HEIGHT, (
            f"the display mode {width}x{height} is below {MIN_WIDTH}x{MIN_HEIGHT}"
        )
        assert page_width >= MIN_WIDTH and page_height >= MIN_HEIGHT, (
            f"the page is laid out at {page_width}x{page_height}, below {MIN_WIDTH}x{MIN_HEIGHT}"
        )
