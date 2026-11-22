"""The board's consoles, and a keyboard attached to type into them."""

from dataclasses import dataclass

from board.console.keyboard import Keyboard
from board.console.terminals import Terminals


@dataclass
class Console:
    """The board's consoles: its virtual terminals, and an evemu keyboard typing into them.

    Attributes:
        terminals: the virtual terminals.
        keyboard: the evemu keyboard typing into them.
    """

    terminals: Terminals
    keyboard: Keyboard
