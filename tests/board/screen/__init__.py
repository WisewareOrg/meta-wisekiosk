"""The board's screen, as the panel shows it."""

from typing import TYPE_CHECKING

from board.screen.captures import Captures

if TYPE_CHECKING:
    from board import Board


class Screen:
    """The board's screen: screenshots of what the panel shows.

    Attributes:
        captures: screenshots of the panel's middle third.
    """

    captures: Captures

    def __init__(self, board: "Board") -> None:
        """Build the screen's parts on `board`.

        Args:
            board: the board under test.
        """
        self.captures = Captures(board)
