"""Target suite: the board's own config file is byte for byte the same after an update, a restart and a power cut."""

from collections.abc import Callable

import pytest
from board import Board


def _check(record_property: Callable[[str, object], None], hashes: tuple[str | None, str | None, str | None]) -> None:
    """Record the three hashes and the validity, then assert the config held.

    It also asserts that a loss would have been seen.

    Args:
        record_property: the test's `record_property`; the hashes are recorded first, then `validity`.
        hashes: the sha256 of the live config before the fault and after it, and of the image default
            the board reseeds from; each None if the file is missing.
    """
    before, after, default = hashes
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


def test_config_held_across_image_update(
    config_across_update: tuple[str | None, str | None, str | None] | None,
    bench_candidate: str | None,
    record_property: Callable[[str, object], None],
) -> None:
    """The config the board held before the candidate's image update is the one it holds after.

    Args:
        config_across_update: the config's hashes before and after the start-of-run install.
        bench_candidate: the commit under test, or None outside a build.
        record_property: records the requirement and the hashes.
    """
    if bench_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    record_property("requirement", "TST019")
    _check(record_property, config_across_update)


def test_config_held_across_restart(board: Board, record_property: Callable[[str, object], None]) -> None:
    """The config the board held before `Board.restart` is the one it holds after.

    Args:
        board: the board under test, restarted here.
        record_property: records the requirement and the hashes.
    """
    record_property("requirement", "TST020")
    before = board.sha256(board.CONFIG_PATH)
    default = board.sha256(board.DEFAULT_CONFIG_PATH)
    board.restart()
    after = board.sha256(board.CONFIG_PATH)
    _check(record_property, (before, after, default))


def test_config_held_across_power_cut(
    board: Board, power_cut: Callable[[], float], record_property: Callable[[str, object], None]
) -> None:
    """The config the board held before its power was cut is the one it holds after.

    Args:
        board: the board under test, whose power is cut.
        power_cut: cuts the power and returns the instant it came back.
        record_property: records the requirement and the hashes.
    """
    record_property("requirement", "TST021")
    before = board.sha256(board.CONFIG_PATH)
    default = board.sha256(board.DEFAULT_CONFIG_PATH)
    power_cut()
    after = board.sha256(board.CONFIG_PATH)
    _check(record_property, (before, after, default))
