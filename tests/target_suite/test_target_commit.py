"""Target suite: the booted image update names the commit it was built from."""

from collections.abc import Callable

import pytest
from board import Board


def test_buildinfo_names_commit(
    board: Board, bench_candidate: str | None, record_property: Callable[[str, object], None]
) -> None:
    """After an image update, /etc/buildinfo names the installed commit.

    Args:
        board: the board under test, whose build info is read.
        bench_candidate: the commit under test, or None outside a build.
        record_property: records the requirement.
    """
    if bench_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    record_property("requirement", "TST016")
    expected = bench_candidate
    commit = board.build_commit()
    assert commit == expected, f"board reports commit {commit}, expected {expected} (bench_candidate)"
