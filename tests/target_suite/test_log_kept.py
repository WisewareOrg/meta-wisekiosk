"""Target suite: the board's log holds a line written before an image update."""

import pytest


def test_log_kept(board, install_candidate, record_property):
    """TST028 log kept: a marker written before the start-of-run install is in the log after it."""
    if install_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    record_property("requirement", "TST028")
    marker, seen_before = install_candidate
    assert seen_before, "the marker never reached the log before the update"
    stdout, _stderr, returncode = board.run("journalctl -t kiosk-log-marker -o cat")
    assert returncode == 0, "reading the log failed"
    assert marker in stdout, "the marker is not in the log after the update"
