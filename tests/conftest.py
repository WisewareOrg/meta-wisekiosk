"""Shared setup: the `Board` the tests drive, and getting it onto `bench_candidate`."""

import uuid

import pytest
from board import Board
from labgrid import Target


@pytest.fixture(scope="session")
def board(target: Target) -> Board:
    """The `Board` for the target.

    Args:
        target: names the board's SSHDriver and NetworkService.

    Returns:
        The board under test.
    """
    return Board(target)


@pytest.fixture(scope="session")
def install_candidate(bench_candidate: str | None, board: Board) -> tuple[str, bool] | None:
    """Install `bench_candidate` on the board, if there is one, then print its commit.

    Before the install, writes a uuid marker line to the board's journal under the identifier
    `kiosk-log-marker` and polls for up to 10 s, once a second, until it reads that line back. The
    fixture never asserts on that read. Installs by `board.install_image`, then `board.restart`.
    Either way, prints the board's meta-wisekiosk commit as `board_commit=<sha>`.

    Args:
        bench_candidate: the commit under test, or None outside a build.
        board: the board under test.

    Returns:
        The marker and whether the journal held it before the install; None outside a build.
    """
    marked = None
    if bench_candidate is not None:
        marker = str(uuid.uuid4())
        board.run(f"echo {marker} | systemd-cat -t kiosk-log-marker", check=True)
        seen_s, _ = board.wait_until(
            lambda: marker in board.run("journalctl -t kiosk-log-marker -o cat")[0] or None, bool, 10
        )
        marked = (marker, seen_s is not None)
        board.install_image()
        board.restart()
    print(f"board_commit={board.commit()}")
    return marked
