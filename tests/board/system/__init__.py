"""The board's operating system, as tests read and set it."""

from typing import TYPE_CHECKING

from board.system.soak import Soak

if TYPE_CHECKING:
    from board import Board


class System:
    """The board's operating system: the kiosk-soak sampler.

    Attributes:
        soak: the kiosk-soak sampler, its timer and its log.
    """

    soak: Soak

    def __init__(self, board: "Board") -> None:
        """Build the system's parts on `board`.

        Args:
            board: the board under test.
        """
        self.soak = Soak(board)
