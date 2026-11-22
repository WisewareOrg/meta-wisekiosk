"""Target suite: the display server's screen saver and power management are off."""

from board_test import BoardTest


class TestDisplayBlanking(BoardTest):
    """The display server never blanks the panel."""

    def test_display_blanking_disabled(self) -> None:
        """TST007 display blanking disabled: `xset q` shows a zero screen-saver timeout and DPMS off."""
        self.record(requirement="TST007")

        xset_text, screen_saver_timeout_s, dpms_disabled = self.board.screen.display.xset_query()

        self.record(xset_q=xset_text)
        assert screen_saver_timeout_s is not None, f"no screen saver timeout in xset's output: {xset_text!r}"
        assert screen_saver_timeout_s == 0, f"the screen saver timeout is {screen_saver_timeout_s} s, not 0"
        assert dpms_disabled, f"display power management is not off; xset q reads: {xset_text!r}"
