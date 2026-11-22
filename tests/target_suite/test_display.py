"""Target suite: the panel shows only the instance, at the minimum resolution."""

import re

from board_test import BoardTest

# TST031's floor
_MIN_WIDTH = 1280
_MIN_HEIGHT = 720


class TestDisplay(BoardTest):
    """The panel shows only the instance, with no pointer, at the minimum resolution."""

    def setup_method(self) -> None:
        """Put the probe in the browser."""
        self.record(probe_sha256=self.board.app.page.install_probe())

    def test_pointer_display_disabled(self) -> None:
        """TST013 pointer display disabled: read X's start-up options and require `-nocursor`."""
        self.record(requirement="TST013")
        self.board.app.page.wait_for_instance()

        options = self.board.screen.display.x_server_options()

        self.record(x_cmdline="\n".join(options))
        assert "-nocursor" in options, f"X runs without -nocursor: {options}"

    def test_instance_covers_the_panel(self) -> None:
        """TST030 instance covers the panel: its window contains the panel and nothing shown overlies it."""
        self.record(requirement="TST030")
        self.board.app.page.wait_for_instance()

        outputs, windows, xrandr, windows_text = self.board.screen.display.window_layout()

        self.record(xrandr=xrandr, window_layout=windows_text)
        assert outputs, "no connected output with a mode"
        assert len(outputs) == 1, f"more than one connected output: {outputs}"
        panel_area = outputs[0]
        instances = [index for index, window in enumerate(windows) if "WK1 " in window.name]
        assert instances, "no window carries the instance's title"
        assert len(instances) == 1, (
            f"more than one window carries the instance's title: {[windows[i].id for i in instances]}"
        )
        instance = windows[instances[0]]
        assert instance.map_state == "IsViewable", f"the instance's window is {instance.map_state}"
        assert instance.contains(panel_area), (
            f"the instance's window {instance.width}x{instance.height}+{instance.x}+{instance.y} "
            f"does not contain the panel {panel_area.width}x{panel_area.height}+{panel_area.x}+{panel_area.y}"
        )
        for above in windows[: instances[0]]:
            assert above.map_state != "IsViewable" or not above.overlaps(panel_area), (
                f"window {above.id} {above.name!r} {above.width}x{above.height}+{above.x}+{above.y} "
                "is shown above the instance and overlaps the panel"
            )

    def test_minimum_resolution(self) -> None:
        """TST031 minimum resolution: the display mode and the page's layout size are each at least 1280x720."""
        self.record(requirement="TST031")
        _uptime_s, sample = self.board.app.page.wait_for_instance()
        self.record(layout=sample["layout"])

        xrandr, mode_lines, mode_width, mode_height = self.board.screen.display.mode()

        self.record(xrandr=xrandr)
        assert mode_lines, "xrandr reports no current mode"
        assert len(mode_lines) == 1, f"more than one current mode: {mode_lines}"
        assert mode_width is not None, f"xrandr's current mode line is unreadable: {mode_lines[0]!r}"
        layout = re.match(r"^(\d+)x(\d+)$", sample["layout"])
        assert layout, f"the probe's layout is unreadable: {sample['layout']!r}"
        layout_width, layout_height = int(layout.group(1)), int(layout.group(2))
        assert mode_width >= _MIN_WIDTH, f"display mode width {mode_width} is below {_MIN_WIDTH}"
        assert mode_height >= _MIN_HEIGHT, f"display mode height {mode_height} is below {_MIN_HEIGHT}"
        assert layout_width >= _MIN_WIDTH, f"layout width {layout_width} is below {_MIN_WIDTH}"
        assert layout_height >= _MIN_HEIGHT, f"layout height {layout_height} is below {_MIN_HEIGHT}"
