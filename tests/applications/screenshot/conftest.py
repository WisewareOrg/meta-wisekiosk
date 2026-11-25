"""Screenshot suite setup: a board running the candidate, for the test that needs one."""

from collections.abc import Iterator

import pytest
from board import Board
from board.updates import Installed
from labgrid import Target


@pytest.fixture
def board(install_candidate: Installed | None, target: Target) -> Iterator[Board]:
    """The board under test, after the start-of-run install.

    Args:
        install_candidate: the start-of-run install.
        target: the board's labgrid target.

    Yields:
        Board: the board; what the test registered on its cleanup is undone once it ends.
    """
    with Board(target) as board:
        yield board
