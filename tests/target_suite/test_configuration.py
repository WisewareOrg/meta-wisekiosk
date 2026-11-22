"""Target suite: the board's own config file is byte for byte the same after an update, a restart and a power cut."""

import pytest


def _check(before, after, default, record_property):
    """Record the three hashes and the validity, then assert the config held.

    It also asserts that a loss would have been seen.

    Args:
        before (str | None): sha256 of the live config before the fault.
        after (str | None): sha256 of the live config after it.
        default (str | None): sha256 of the image default the board reseeds from.
        record_property (Callable): the test's `record_property`; the hashes are recorded
            first, then `validity`.
    """
    record_property("config_before_sha256", before)
    record_property("config_after_sha256", after)
    record_property("config_default_sha256", default)
    if before is None:
        validity = "invalid: the board held no config.json to keep"
    elif after != before:
        validity = "valid"
    elif default is None or before == default:
        validity = "invalid: the board's config is the image default, or the default is unreadable"
    else:
        validity = "valid"
    record_property("validity", validity)
    assert before is not None, "INVALID CHECK, not an appliance failure: the board held no config.json to keep"
    assert after == before, f"config held {'missing' if after is None else after}, expected the {before} it held before"
    assert default is not None, "INVALID CHECK, not an appliance failure: the image default could not be read"
    assert before != default, (
        "INVALID CHECK, not an appliance failure: the board's config is the image default, so losing it would go unseen"
    )


def test_config_held_across_image_update(config_across_update, bench_candidate, record_property):
    """The config the board held before the candidate's image update is the one it holds after."""
    if bench_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    before, after, default = config_across_update
    record_property("requirement", "TST019")
    _check(before, after, default, record_property)


def test_config_held_across_restart(board, record_property):
    """The config the board held before `just kiosk-reboot` is the one it holds after."""
    record_property("requirement", "TST020")
    before = board.sha256(board.CONFIG_PATH)
    default = board.sha256(board.DEFAULT_CONFIG_PATH)
    board.restart()
    after = board.sha256(board.CONFIG_PATH)
    _check(before, after, default, record_property)


def test_config_held_across_power_cut(board, power_cut, record_property):
    """The config the board held before its power was cut is the one it holds after."""
    record_property("requirement", "TST021")
    before = board.sha256(board.CONFIG_PATH)
    default = board.sha256(board.DEFAULT_CONFIG_PATH)
    power_cut()
    after = board.sha256(board.CONFIG_PATH)
    _check(before, after, default, record_property)
