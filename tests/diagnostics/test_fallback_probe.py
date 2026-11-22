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


def _booted_bootname(board: Board) -> str:
    """The bootname of the slot the board booted from, as `rauc status` names it.

    Args:
        board: the board under test.

    Returns:
        The bootname.
    """
    stdout = board.run("rauc status --output-format=json", check=True, timeout=None)[0]
    return json.loads("\n".join(stdout))["booted"]


def test_fallback_probe(board: Board, record_property: Callable[[str, object], None]) -> None:
    """A slot with no attempts left is skipped and the board boots the other slot.

    Args:
        board: the board under test, restarted here.
        record_property: records the slot states before, after the install and after the restart.
    """
    booted = _booted_bootname(board)
    other = ({"A", "B"} - {booted}).pop()
    record_property("booted", booted)
    record_property("before", json.dumps(board.boot_variables()))

    board.install_image()
    order, left = board.boot_variables()
    record_property("installed", json.dumps([order, left]))
    assert order[0] == other, f"slot {other} does not lead BOOT_ORDER after the install: {order}"
    assert left[other] > 0, f"slot {other} has no attempts left after the install"

    board.run(f"fw_setenv BOOT_{other}_LEFT 0", check=True)
    board.restart_by("systemctl reboot")

    order, left = board.boot_variables()
    record_property("after", json.dumps([order, left]))
    assert _booted_bootname(board) == booted, f"the board is not back on slot {booted}"
    assert order[0] == other, f"slot {other} no longer leads BOOT_ORDER: {order}"
    assert left[other] == 0, f"slot {other} has {left[other]} attempts left, not 0"
