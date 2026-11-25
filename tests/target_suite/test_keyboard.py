"""Target suite: with the network gone, a keyboard attached to the board gives a shell at a console the panel shows."""

from board_test import BoardTest


class TestKeyboard(BoardTest):
    """With the network gone, a keyboard attached to the board gives a shell at a console the panel shows."""

    def test_shell_from_an_attached_keyboard(self) -> None:
        """TST027: with the network cut off, log in at the console with an attached keyboard and type a command.

        The panel must show the console both when the command has run and once the outage has ended.
        """
        self.record(requirement="TST027")

        typed = self.board.console.type_offline()

        self.record(
            terminal=typed.marker.terminal,
            word_written=typed.marker.word,
            keyboard_progress=typed.progress,
            panel_when_typed=str(typed.panel_when_typed),
            panel=str(typed.panel),
        )
        assert typed.marker.terminal == "/dev/tty2", f"the command did not run at tty2's login: {typed}"
        assert typed.marker.word == typed.word, f"the command ran, but did not write what was typed: {typed}"
        assert [plane.allocated_by for plane in typed.panel_when_typed] == ["fbcon"], (
            f"when the command had run the panel showed {typed.panel_when_typed}, not the console"
        )
        assert [plane.allocated_by for plane in typed.panel] == ["fbcon"], (
            f"once the outage had ended the panel showed {typed.panel}, not the console"
        )
