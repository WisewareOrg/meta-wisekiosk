"""Shared setup: getting the board onto `bench_candidate` at the start of a run."""

import uuid

import pytest
from board import Board
from labgrid import Target

LOG_MARKER_WAIT_SECONDS = 10


@pytest.fixture(scope="session")
def install_candidate(bench_candidate: str | None, target: Target) -> tuple[str, bool] | None:
    """Install `bench_candidate` on the board, if there is one, then print its commit.

    Works through a board of its own. Before the install, writes a uuid marker line to the board's
    journal under the identifier `kiosk-log-marker` and polls for up to `LOG_MARKER_WAIT_SECONDS`,
    once a second, until it reads that line back; it never asserts on that read. Installs with
    `just kiosk-ota`, then reboots with `just kiosk-reboot`. Either way, prints the board's
    meta-wisekiosk commit as `board_commit=<sha>`.

    Args:
        bench_candidate: the commit under test, or None outside a build.
        target: the board's labgrid target.

    Returns:
        The marker and whether the journal held it before the install; None outside a build.
    """
    marked = None
    with Board(target) as board:
        if bench_candidate is not None:
            marker = str(uuid.uuid4())
            board.system.journal.write_marker(marker)
            seen_s, _ = board.poll(
                lambda: marker in (board.system.journal.markers() or []) or None,
                until=bool,
                within=LOG_MARKER_WAIT_SECONDS,
            )
            marked = (marker, seen_s is not None)
            board.updates.install_built_image()
            board.reboot()
        print(f"board_commit={board.updates.build_commit()}")
    return marked
