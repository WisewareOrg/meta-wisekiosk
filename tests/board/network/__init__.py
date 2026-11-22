"""The board's network, as tests take it away and load it."""

from dataclasses import dataclass

from board.network.load import Load
from board.network.outage import Outage


@dataclass
class Network:
    """The board's network: an outage scheduled on the board, and a load pushed at it.

    Attributes:
        outage: a scheduled network outage and its record.
        load: bytes pushed at the board.
    """

    outage: Outage
    load: Load
