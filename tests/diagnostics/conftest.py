"""Diagnostics setup: the start-of-run install, and a board for each diagnostic."""

from collections.abc import Iterator

import pytest
from board import Board
from labgrid import Target


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(bench_candidate: str | None, request: pytest.FixtureRequest, target: Target) -> None:
    """Activate `install_candidate` (tests/conftest.py) for every test in this suite, when there is a build.

    Under `--skip-build` there is no candidate, so nothing is cleared and nothing is installed; the
    board's commit is still printed as `board_commit=<sha>`.

    Args:
        bench_candidate: the commit under test, or None outside a build.
        request: the pytest request, which activates `install_candidate`.
        target: the board's labgrid target.
    """
    if bench_candidate is not None:
        request.getfixturevalue("install_candidate")
        return
    with Board(target) as board:
        print(f"board_commit={board.updates.build_commit()}")


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
