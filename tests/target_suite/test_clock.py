"""Target suite: a clock set wrong by days and persisted across a restart is corrected."""

import subprocess
import time

import pytest

from page import POLL_ATTEMPT_TIMEOUT_SECONDS, POLL_INTERVAL_SECONDS

# placeholder for the measurement runs; the real bound is set from them
BOUND_SECONDS = 600
AGREE_SECONDS = 5
SKEW_SECONDS = 3 * 24 * 3600
STILL_WRONG_SECONDS = 24 * 3600
CLOCK_FILE = "/data/systemd-timesync/clock"


def _run_checked(driver, cmd):
    """Run `cmd` on the board and assert it returned 0.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.
        cmd (str): the command to run.

    Returns:
        list[str]: `cmd`'s combined stdout and stderr lines.

    Raises:
        AssertionError: `cmd` returned nonzero.
    """
    stdout, stderr, returncode = driver.run(cmd, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
    output = stdout + stderr
    assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
    return output


def _board_offset(driver):
    """The board's clock minus the host's, in seconds.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.

    Returns:
        float: board `date +%s` minus host `time.time()`.

    Raises:
        AssertionError: the board's clock cannot be read.
    """
    stdout = _run_checked(driver, "date +%s")
    return int(stdout[0].strip()) - time.time()


def _set_board_clock(driver, epoch):
    """Set the board's clock to `epoch` and record it as the persisted clock.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.
        epoch (int): seconds since the epoch.

    Raises:
        AssertionError: setting the clock or touching the clock file fails.
    """
    _run_checked(driver, f"date -s @{epoch}")
    _run_checked(driver, f"touch {CLOCK_FILE}")


@pytest.fixture
def restore_clock(target):
    """Leave the board's clock agreeing with the host's and timesyncd running, at teardown.

    Args:
        target (labgrid.Target): names the board's SSHDriver.
    """
    driver = target.get_driver("SSHDriver")
    yield
    if abs(_board_offset(driver)) > AGREE_SECONDS:
        _set_board_clock(driver, int(time.time()))
    _run_checked(driver, "systemctl start systemd-timesyncd")


def test_clock_set_wrong(target, restore_clock, record_property):
    """The board's clock agrees with the host's within `BOUND_SECONDS` of a restart.

    Stops timesyncd, sets the clock three days back and records it as the persisted clock,
    then restarts the board. The check is invalid unless the first clock read after the
    restart is still more than a day off.
    """
    service = target.get_resource("NetworkService")
    host = f"{service.username}@{service.address}"
    driver = target.get_driver("SSHDriver")

    _run_checked(driver, "systemctl stop systemd-timesyncd")
    _set_board_clock(driver, int(time.time()) - SKEW_SECONDS)

    started = time.monotonic()
    subprocess.run(["just", "kiosk-reboot", host], check=True)
    target.deactivate(driver)
    target.activate(driver)

    offset = _board_offset(driver)
    assert abs(offset) > STILL_WRONG_SECONDS, (
        f"INVALID CHECK, not an appliance failure: the clock was not still wrong after the "
        f"restart (offset {offset:.0f}s)"
    )

    elapsed = time.monotonic() - started
    while abs(offset) > AGREE_SECONDS and elapsed <= BOUND_SECONDS:
        time.sleep(POLL_INTERVAL_SECONDS)
        offset = _board_offset(driver)
        elapsed = time.monotonic() - started

    stdout, stderr, _returncode = driver.run(
        "journalctl -b -u systemd-timesyncd --no-pager", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS
    )
    print("\n".join(stdout + stderr))
    print(f"clock_corrected_seconds={elapsed:.1f} final_offset_seconds={offset:.1f}")
    record_property("clock_corrected_seconds", elapsed)
    assert abs(offset) <= AGREE_SECONDS, (
        f"clock still {offset:.0f}s off the network's time {BOUND_SECONDS}s after the restart"
    )
    assert elapsed <= BOUND_SECONDS, f"clock agreed only after {elapsed:.0f}s, bound {BOUND_SECONDS}s"
    record_property("requirement", "TST015")
