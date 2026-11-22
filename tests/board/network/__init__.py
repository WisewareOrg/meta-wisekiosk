"""The board's network, as tests take it away and load it."""

from typing import TYPE_CHECKING

from board.network.load import Load
from board.network.outage import Outage

if TYPE_CHECKING:
    from board import Board


class Network:
    """The board's network: an outage scheduled on the board, and a load pushed at it.

    Attributes:
        outage: a scheduled network outage and its record.
        load: bytes pushed at the board.
    """

    outage: Outage
    load: Load

    def __init__(self, board: "Board") -> None:
        """Build the network's parts on `board`.

        Args:
            board: the board under test.
        """
        self.outage = Outage(board)
        self.load = Load(board)
