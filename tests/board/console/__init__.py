"""The board's consoles, and a keyboard attached to type into them."""

from typing import TYPE_CHECKING

from board.console.keyboard import Keyboard
from board.console.terminals import Terminals

if TYPE_CHECKING:
    from board import Board


class Console:
    """The board's consoles: its virtual terminals, and an evemu keyboard typing into them.

    Attributes:
        terminals: the virtual terminals.
        keyboard: the evemu keyboard typing into them.
    """

    terminals: Terminals
    keyboard: Keyboard

    def __init__(self, board: "Board") -> None:
        """Build the console's parts on `board`.

        Args:
            board: the board under test.
        """
        self.terminals = Terminals(board)
        self.keyboard = Keyboard(board)
