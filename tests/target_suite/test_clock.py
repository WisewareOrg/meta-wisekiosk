"""Target suite: a clock set wrong by days and persisted across a restart is corrected."""

import json
import subprocess
import time

import pytest

from page import POLL_ATTEMPT_TIMEOUT_SECONDS, POLL_INTERVAL_SECONDS

# the bound is TST015's
BOUND_SECONDS = 110
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


def _restored_clock_offset(driver):
    """How far behind the host the clock was when timesyncd first logged this boot.

    timesyncd restores the recorded clock at its own startup, before it logs anything, so
    its earliest entry this boot carries the restored clock. Filters on the syslog
    identifier rather than the unit, which would also match systemd's own earlier entries.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.

    Returns:
        float | None: host `time.time()` minus that entry's realtime in seconds, or None if
            timesyncd logged nothing this boot.

    Raises:
        AssertionError: the journal cannot be read.
    """
    lines = _run_checked(
        driver, "journalctl -b SYSLOG_IDENTIFIER=systemd-timesyncd -o json --no-pager"
    )
    if not lines:
        return None
    return time.time() - int(json.loads(lines[0])["__REALTIME_TIMESTAMP"]) / 1e6


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
    then restarts the board. The check is invalid unless this boot's timesyncd journal shows
    timesyncd's first entry carries a clock more than a day behind the host.
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

    behind = _restored_clock_offset(driver)
    assert behind is not None, (
        "INVALID CHECK, not an appliance failure: timesyncd logged nothing this boot"
    )
    assert behind > STILL_WRONG_SECONDS, (
        f"INVALID CHECK, not an appliance failure: timesyncd's first entry was not stamped wrong "
        f"(only {behind:.0f}s behind the host)"
    )

    offset = _board_offset(driver)
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
