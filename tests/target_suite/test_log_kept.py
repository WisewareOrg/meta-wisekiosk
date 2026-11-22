"""Target suite: the board's log holds a line written before an image update."""

from collections.abc import Callable

import pytest
from board import Board


def test_log_kept(
    board: Board,
    install_candidate: tuple[str, bool] | None,
    record_property: Callable[[str, object], None],
) -> None:
    """TST028 log kept: a marker written before the start-of-run install is in the log after it.

    Args:
        board: the board under test, whose journal is read.
        install_candidate: the marker and whether the journal held it before the install; None
            outside a build.
        record_property: records the requirement.
    """
    if install_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    record_property("requirement", "TST028")
    marker, seen_before = install_candidate
    assert seen_before, "the marker never reached the log before the update"
    stdout, _stderr, returncode = board.run("journalctl -t kiosk-log-marker -o cat")
    assert returncode == 0, "reading the log failed"
    assert marker in stdout, "the marker is not in the log after the update"
