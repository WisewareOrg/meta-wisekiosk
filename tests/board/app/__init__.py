"""The WiseKiosk app on the board."""

from typing import TYPE_CHECKING

from board.app.backend import Backend
from board.app.page import Page

if TYPE_CHECKING:
    from board import Board


class App:
    """The WiseKiosk app on the board, end to end: its backend and its page.

    Attributes:
        backend: wisekiosk.service.
        page: the app's page in the browser.
    """

    backend: Backend
    page: Page

    def __init__(self, board: "Board") -> None:
        """Build the app's parts on `board`.

        Args:
            board: the board under test.
        """
        self.backend = Backend(board)
        self.page = Page(board)
