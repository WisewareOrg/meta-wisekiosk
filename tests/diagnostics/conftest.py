"""Diagnostics setup: the start-of-run install, and a board for each diagnostic."""

from collections.abc import Iterator

import pytest
from board import Board
from board.updates import Installed
from labgrid import Target


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(install_candidate: Installed | None) -> None:
    """Activate `install_candidate` (tests/conftest.py) for every test in this suite.

    Args:
        install_candidate: the start-of-run install.
    """


@pytest.fixture
def board(target: Target, request: pytest.FixtureRequest) -> Iterator[Board]:
    """The board under test, for one diagnostic.

    Args:
        target: the board's labgrid target.
        request: the diagnostic's own request, for the fixtures the board reaches on demand.

    Yields:
        Board: the board; what the diagnostic registered on its cleanup is undone once it ends.
    """
    with Board(target, fixtures=request.getfixturevalue) as board:
        yield board
