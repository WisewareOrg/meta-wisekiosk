"""Target suite: the booted image update names the commit it was built from."""

import pytest


def test_buildinfo_names_commit(board, bench_candidate, record_property):
    """After an image update, /etc/buildinfo names the installed commit."""
    if bench_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    record_property("requirement", "TST016")
    expected = bench_candidate
    commit = board.commit()
    assert commit == expected, f"board reports commit {commit}, expected {expected} (bench_candidate)"
