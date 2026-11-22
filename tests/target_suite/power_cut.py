"""A power cut through the bench's switched plug: off, a pause, on, and the board back in a new boot."""

import subprocess
import time

import pytest

_POWER_OFF_SECONDS = 10


def cut_power(board, power, record_property):
    """Cut the board's power, restore it, and reconnect once the board answers in a new boot.

    Args:
        board (Board): the board under test (tests/conftest.py).
        power (labgrid.driver.ExternalPowerDriver): the bench's switched plug.
        record_property (Callable): the test's `record_property`; records `power_on_command_s`.

    Returns:
        float: the host `time.monotonic()` at which the `on` command started. Power returns no
            earlier, so a time taken from it errs high.
    """
    old_boot_id = board.run(board.BOOT_ID_CMD, check=True)[0][0]
    board.disconnect()
    try:
        power.off()
        time.sleep(_POWER_OFF_SECONDS)
        on_began = time.monotonic()
        power.on()
    except (subprocess.CalledProcessError, OSError) as error:
        pytest.exit(f"the bench's power switch failed: {error}", returncode=2)
    record_property("power_on_command_s", round(time.monotonic() - on_began, 1))
    board.reconnect()
    if board.run(board.BOOT_ID_CMD, check=True)[0][0] == old_boot_id:
        pytest.exit(
            f"the board answered in the same boot after {_POWER_OFF_SECONDS} s off: "
            "the plug or its supply did not cut power",
            returncode=2,
        )
    return on_began
