"""The WiseKiosk app on the board."""

from dataclasses import dataclass

from board.app.backend import Backend
from board.app.config import Config
from board.app.page import Page


@dataclass(kw_only=True)
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
