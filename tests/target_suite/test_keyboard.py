"""Target suite: with the network gone, a keyboard attached to the board gives a shell at its console."""

from board_test import BoardTest


class TestKeyboard(BoardTest):
    """With the network gone, a keyboard attached to the board gives a shell at its console."""

    def test_shell_from_an_attached_keyboard(self) -> None:
        """TST027: with the network cut off, log in at the console with an attached keyboard and type a command."""
        self.record(requirement="TST027")

        typed = self.board.console.type_offline()

        self.record(terminal=typed.marker.terminal, word_written=typed.marker.word, keyboard_progress=typed.progress)
        assert typed.marker.terminal == "/dev/tty2", f"the command did not run at tty2's login: {typed}"
        assert typed.marker.word == typed.word, f"the command ran, but did not write what was typed: {typed}"
