"""The board's operating system, as tests read and set it."""

from typing import TYPE_CHECKING

from board.system.memory import Memory
from board.system.soak import Soak

if TYPE_CHECKING:
    from board import Board


class System:
    """The board's operating system: its memory, and the kiosk-soak sampler.

    Attributes:
        memory: memory and the kernel's out-of-memory record.
        soak: the kiosk-soak sampler, its timer and its log.
    """

    memory: Memory
    soak: Soak

    def __init__(self, board: "Board") -> None:
        """Build the system's parts on `board`.

        Args:
            board: the board under test.
        """
        self.memory = Memory(board)
        self.soak = Soak(board)
