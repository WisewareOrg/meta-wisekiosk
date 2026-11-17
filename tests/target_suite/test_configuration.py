"""Target suite: a changed configuration file is held byte for byte across an image update and a restart."""

import pytest


def _assert_held(written, held):
    assert held == written, (
        f"config held {'missing' if held is None else held}, expected the written {written}"
    )


def test_config_held_across_image_update(config_across_update, bench_candidate, record_property):
    """The config written before the candidate's image update is the one the board holds after it."""
    if bench_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    written, held = config_across_update
    record_property("requirement", "TST019")
    record_property("config_written_sha256", written)
    record_property("config_held_sha256", held)
    _assert_held(written, held)


def test_config_held_across_restart(changed_config, board, record_property):
    """The config written before `just kiosk-reboot` is the one the board holds after it."""
    record_property("requirement", "TST020")
    board.restart()
    held = changed_config.held_sha256()
    record_property("config_written_sha256", changed_config.written_sha256)
    record_property("config_held_sha256", held)
    _assert_held(changed_config.written_sha256, held)
