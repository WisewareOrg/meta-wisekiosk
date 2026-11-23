"""Target suite: the panel shows nothing but the instance, at the minimum resolution."""

from board_test import BoardTest

# TST031's floor
MIN_WIDTH, MIN_HEIGHT = 1280, 720


class TestDisplay(BoardTest):
    """The panel shows only the instance, with no pointer, at the minimum resolution."""

    def setup_method(self) -> None:
        """Put the probe in the browser, and wait for the instance on the panel."""
        self.board.app.install_probe()
        self.board.app.wait_until_on_panel()

    def test_pointer_display_disabled(self) -> None:
        """TST013: the options the display server was started with disable the pointer's display."""
        self.record(requirement="TST013")

        options = self.board.screen.x_server_options()

        self.record(x_server_options=" ".join(options))
        assert "-nocursor" in options, f"X runs without -nocursor: {options}"

    def test_instance_covers_the_panel(self) -> None:
        """TST030: the instance's window is shown over the whole panel, and no window shown above it overlaps it."""
        self.record(requirement="TST030")

        layout = self.board.screen.window_layout()

        self.record(window_layout=layout.text)
        instance, panel = layout.instance, layout.panel
        assert instance.shown, f"the instance's window is {instance.map_state}"
        assert instance.contains(panel), f"the instance's window {instance} does not cover the panel {panel}"
        overlapping = [window for window in layout.above(instance) if window.shown and window.overlaps(panel)]
        assert not overlapping, f"shown above the instance and over the panel: {overlapping}"

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
