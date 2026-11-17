"""Target suite: the board's own configuration file is byte for byte the same after an image update and a restart."""

import pytest

_CONFIG_PATH = "/data/config/config.json"
_DEFAULT_CONFIG_PATH = "/usr/share/wisekiosk/config.example.json"


def _check(before, after, default):
    """Assert the config held, and that a loss would have been seen.

    Args:
        before (str | None): sha256 of the live config before the update or restart.
        after (str | None): sha256 of the live config after it.
        default (str | None): sha256 of the image default the board reseeds from.
    """
    assert before is not None, "INVALID CHECK, not an appliance failure: the board held no config.json to keep"
    assert after == before, (
        f"config held {'missing' if after is None else after}, expected the {before} it held before"
    )
    assert before != default, (
        "INVALID CHECK, not an appliance failure: the board's config is the image default, "
        "so losing it would go unseen"
    )


def test_config_held_across_image_update(config_across_update, bench_candidate, record_property):
    """The config the board held before the candidate's image update is the one it holds after."""
    if bench_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    before, after, default = config_across_update
    record_property("requirement", "TST019")
    record_property("config_before_sha256", before)
    record_property("config_after_sha256", after)
    record_property("config_default_sha256", default)
    _check(before, after, default)


def test_config_held_across_restart(board, record_property):
    """The config the board held before `just kiosk-reboot` is the one it holds after."""
    record_property("requirement", "TST020")
    before = board.sha256(_CONFIG_PATH)
    default = board.sha256(_DEFAULT_CONFIG_PATH)
    board.restart()
    after = board.sha256(_CONFIG_PATH)
    record_property("config_before_sha256", before)
    record_property("config_after_sha256", after)
    record_property("config_default_sha256", default)
    _check(before, after, default)
