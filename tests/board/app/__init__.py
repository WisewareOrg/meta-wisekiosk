"""The WiseKiosk app on the board."""

from typing import TYPE_CHECKING

from board.app.backend import Backend
from board.app.config import Config
from board.app.page import Page

if TYPE_CHECKING:
    from board import Board


class App:
    """The WiseKiosk app on the board, end to end: its backend, its config and its page.

    Attributes:
        backend: wisekiosk.service.
        config: the config the app runs with.
        page: the app's page in the browser.
    """

    backend: Backend
    config: Config
    page: Page

    def __init__(self, board: "Board") -> None:
        """Build the app's parts on `board`.

        Args:
            board: the board under test.
        """
        self.backend = Backend(board)
        self.config = Config(board)
        self.page = Page(board)
