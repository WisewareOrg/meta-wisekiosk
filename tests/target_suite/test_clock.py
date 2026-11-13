"""Target suite: a clock set wrong by days and persisted across a restart is corrected."""

import json
import subprocess
import time

import pytest

from board import run_checked
from page import POLL_ATTEMPT_TIMEOUT_SECONDS, POLL_INTERVAL_SECONDS

# the bound is TST015's
BOUND_SECONDS = 110
AGREE_SECONDS = 5
SKEW_SECONDS = 3 * 24 * 3600
STILL_WRONG_SECONDS = 24 * 3600
CLOCK_FILE = "/data/systemd-timesync/clock"


def _poll_board(driver):
    """The board's uptime and its clock minus the host's, from one command.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.

    Returns:
        tuple[float, float] | None: the board's uptime in seconds and board `date +%s` minus
            host `time.time()`, or None if the read failed or timed out.
    """
    try:
        stdout, _stderr, returncode = driver.run(
            "cat /proc/uptime; date +%s", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        return None
    if returncode != 0:
        return None
    return float(stdout[0].split()[0]), int(stdout[1].strip()) - time.time()


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
    cmd = "journalctl -q -b SYSLOG_IDENTIFIER=systemd-timesyncd -o json --no-pager"
    stdout, stderr, returncode = driver.run(cmd, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
    assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(stdout + stderr)}"
    if not stdout:
        return None
    return time.time() - int(json.loads(stdout[0])["__REALTIME_TIMESTAMP"]) / 1e6


def _set_board_clock(driver, epoch):
    """Set the board's clock to `epoch` and record it as the persisted clock.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.
        epoch (int): seconds since the epoch.

    Raises:
        AssertionError: setting the clock or touching the clock file fails.
    """
    run_checked(driver, f"date -s @{epoch}")
    run_checked(driver, f"touch {CLOCK_FILE}")


@pytest.fixture
def restore_clock(target):
    """Leave the board's clock agreeing with the host's and timesyncd running, at teardown.

    Args:
        target (labgrid.Target): names the board's SSHDriver.
    """
    driver = target.get_driver("SSHDriver")
    yield
    reading = _poll_board(driver)
    assert reading is not None, "the board's clock could not be read at teardown"
    if abs(reading[1]) > AGREE_SECONDS:
        _set_board_clock(driver, int(time.time()))
    run_checked(driver, "systemctl start systemd-timesyncd")


def test_clock_set_wrong(target, restore_clock, record_property):
    """The board's clock agrees with the host's within `BOUND_SECONDS` of its starting up again.

    Stops timesyncd, sets the clock three days back and records it as the persisted clock,
    then restarts the board and polls until the clock agrees. The time is the board's uptime
    at the first agreeing read. The check is invalid unless this boot's first timesyncd
    journal entry carries the clock the stimulus set, to within a day; that verdict comes
    before the pass conditions.
    """
    record_property("requirement", "TST015")
    service = target.get_resource("NetworkService")
    host = f"{service.username}@{service.address}"
    driver = target.get_driver("SSHDriver")

    run_checked(driver, "systemctl stop systemd-timesyncd")
    _set_board_clock(driver, int(time.time()) - SKEW_SECONDS)

    subprocess.run(["just", "kiosk-reboot", host], check=True)
    returned = time.monotonic()
    target.deactivate(driver)
    target.activate(driver)

    reading = None
    while True:
        latest = _poll_board(driver)
        if latest is not None:
            reading = latest
            uptime, offset = reading
            if abs(offset) <= AGREE_SECONDS or uptime > BOUND_SECONDS:
                break
        elif time.monotonic() - returned > BOUND_SECONDS:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    behind = _restored_clock_offset(driver)
    stdout, stderr, _returncode = driver.run(
        "journalctl -b -u systemd-timesyncd --no-pager", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS
    )
    print("\n".join(stdout + stderr))
    assert behind is not None, (
        "INVALID CHECK, not an appliance failure: timesyncd logged nothing this boot"
    )
    assert abs(behind - SKEW_SECONDS) < STILL_WRONG_SECONDS, (
        f"INVALID CHECK, not an appliance failure: timesyncd's first entry was {behind:.0f}s "
        f"behind the host, not the {SKEW_SECONDS}s the stimulus set"
    )

    assert reading is not None, "the board's clock could not be read after the restart"
    uptime, offset = reading
    print(f"clock_corrected_seconds={uptime:.1f} final_offset_seconds={offset:.1f}")
    record_property("clock_corrected_seconds", uptime)
    assert abs(offset) <= AGREE_SECONDS, (
        f"clock still {offset:.0f}s off the network's time at uptime {uptime:.0f}s, "
        f"bound {BOUND_SECONDS}s"
    )
    assert uptime <= BOUND_SECONDS, f"clock agreed only at uptime {uptime:.0f}s, bound {BOUND_SECONDS}s"
