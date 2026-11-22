"""The board's screen, as the panel shows it."""

from typing import TYPE_CHECKING

from board.screen.captures import Captures
from board.screen.display import Display

if TYPE_CHECKING:
    from board import Board


class Screen:
    """The board's screen: the X server and its output, and screenshots of what the panel shows.

    Attributes:
        display: the X server and the output it drives.
        captures: screenshots of the panel's middle third.
    """

    display: Display
    captures: Captures

    def __init__(self, board: "Board") -> None:
        """Build the screen's parts on `board`.

        Args:
            board: the board under test.
        """
        self.display = Display(board)
        self.captures = Captures(board)
