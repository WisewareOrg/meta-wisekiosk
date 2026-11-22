"""Diagnostics: U-Boot skips a slot whose boot attempts are spent, and boots the other.

Installs a good copy of the candidate in the slot the board did not boot from, zeroes that slot's
attempts, restarts, and checks the board is back on the slot it booted from while the spent slot
still leads `BOOT_ORDER`. Both slots stay bootable, so it strands nothing.

Outside the regression suite: it is a one-off step before any install that is meant to fail, run
through the bench driver:

    bench test <ref> -- tests/diagnostics -k fallback_probe -rP
"""

import json
from collections.abc import Callable

from board import Board


def test_fallback_probe(board: Board, record_property: Callable[[str, object], None]) -> None:
    """A slot with no attempts left is skipped and the board boots the other slot.

    Args:
        board: the board under test.
        record_property: records the slots and the boot variables at each step.
    """
    booted = board.updates.rauc_status()["booted"]
    other = ({"A", "B"} - {booted}).pop()
    record_property("booted", booted)
    record_property("before", json.dumps(board.updates.boot_order()))

    board.updates.install_built_image()
    boot_order = board.updates.boot_order()
    record_property("installed", json.dumps(boot_order))
    assert boot_order.order[0] == other, f"slot {other} does not lead BOOT_ORDER after the install: {boot_order.order}"
    assert boot_order.attempts_left[other] > 0, f"slot {other} has no attempts left after the install"

    board.run(f"fw_setenv BOOT_{other}_LEFT 0", check=True)
    board.restart_with("systemctl reboot")

    boot_order = board.updates.boot_order()
    record_property("after", json.dumps(boot_order))
    assert board.updates.rauc_status()["booted"] == booted, f"the board is not back on slot {booted}"
    assert boot_order.order[0] == other, f"slot {other} no longer leads BOOT_ORDER: {boot_order.order}"
    assert boot_order.attempts_left[other] == 0, (
        f"slot {other} has {boot_order.attempts_left[other]} attempts left, not 0"
    )
