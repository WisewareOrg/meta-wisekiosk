"""Diagnostics setup: the start-of-run install, and a board for each diagnostic."""

from collections.abc import Iterator

import pytest
from board import Board
from labgrid import Target


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(install_candidate: tuple[str, bool] | None) -> None:
    """Activate `install_candidate` (tests/conftest.py) for every test in this suite.

    Args:
        install_candidate: the start-of-run install's marker and whether the log held it.
    """


@pytest.fixture
def board(target: Target) -> Iterator[Board]:
    """The board under test, for one diagnostic.

    Args:
        target: the board's labgrid target.

    Yields:
        Board: the board; what the diagnostic registered on its cleanup is undone once it ends.
    """
    with Board(target) as board:
        yield board
