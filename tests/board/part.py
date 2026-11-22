"""The base of every sub-part of the board."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from board import Board


class Part:
    """One sub-part of the board, which reaches the board through `self._board`."""

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board
