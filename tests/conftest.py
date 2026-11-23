"""Shared setup: getting the board onto `bench_candidate` at the start of a run."""

import contextlib
import uuid

import pytest
from board import Board
from board.updates import Installed
from labgrid import Target


@pytest.fixture(scope="session")
def install_candidate(bench_candidate: str | None, target: Target) -> Installed | None:
    """Clear what a dead run left, install `bench_candidate` on the board if there is one, and print its commit.

    Works through a board of its own. What a dead run can leave in `/run` goes first: a bind mount over
    the live config, and the backend's runtime drop-ins and mask. Before the install, it reads the
    live config's sha256 and writes a uuid marker line to the board's log, then reads the log until
    the line is there, for as long as `Board.seconds_until` waits. It installs with `just kiosk-ota`,
    reboots with `just kiosk-reboot`, and reads the live config's sha256 again, and the new image's
    default's. Either way, it prints the board's meta-wisekiosk commit as `board_commit=<sha>`.

    Args:
        bench_candidate: the commit under test, or None outside a build.
        target: the board's labgrid target.

    Returns:
        The install; None outside a build.
    """
    installed = None
    with Board(target) as board:
        board.unmount_if_mounted(board.app.config.LIVE_PATH)
        board.app.backend.clear_runtime_changes()
        if bench_candidate is not None:
            config_before = board.app.config.sha256()
            marker = str(uuid.uuid4())
            board.system.journal.write_marker(marker)
            marker_logged = False
            with contextlib.suppress(AssertionError):
                board.seconds_until(lambda: marker in board.system.journal.markers())
                marker_logged = True
            board.updates.install_built_image()
            board.reboot()
            config = board.app.config
            installed = Installed(
                bench_candidate, marker, marker_logged, config_before, config.sha256(), config.default_sha256()
            )
        print(f"board_commit={board.updates.build_commit()}")
    return installed
