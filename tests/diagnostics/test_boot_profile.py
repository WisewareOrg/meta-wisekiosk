"""Diagnostics: one boot profile, captured end to end through labgrid and the host analyzer.

A faithful port of the deleted tools/kiosk-bootprofile.sh, reached through `just bootprofile`
(justfiles/device.just) rather than ssh by hand. It reports what it measures and gives no
verdict on it -- meta-wisekiosk/recipes-core/kiosk-bootprof/README.md covers the limits of the
data and why a connection during the observer window below contaminates the measurement.

Outside the regression suite: this is a device procedure, not tied to a TST, and its own
on-board run is its test.
"""

import subprocess
import time
from pathlib import Path

import pytest
from labgrid.driver.exception import ExecutionError

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ANALYZER = (
    _REPO_ROOT / "meta-wisekiosk" / "recipes-core" / "kiosk-bootprof" / "files"
    / "analyze-boot-cpu-io.py"
)
UNIT_SOURCE = Path(__file__).resolve().parent / "kiosk-bootprofile.service"
DEPLOYED_BINARY = (
    _REPO_ROOT / "build" / "tmp-raspberrypi0-wifi" / "deploy" / "images" / "raspberrypi0-wifi"
    / "kiosk-bootprof"
)

# The script's own defaults.
OUTPUT_DIR = "local"
WAIT_SECONDS = 180
BOARD_BINARY_PATH = "/usr/local/bin/kiosk-bootprof"

_UNIT_NAME = "kiosk-bootprofile"
_UNIT_REMOTE = "/etc/systemd/system/kiosk-bootprofile.service"
_ENABLE_LINK = f"/etc/systemd/system/sysinit.target.wants/{_UNIT_NAME}.service"
_BOARD_BIN_DIR = "/usr/local/bin"
_BOARD_LOCAL_DIR = "/usr/local"
_RETRY_ATTEMPTS = 6
_RETRY_INTERVAL_SECONDS = 20
_CLEANUP_BOUND_SECONDS = 60
_CLEANUP_POLL_SECONDS = 5


def _boot_id(board):
    """Read the board's current boot id.

    Args:
        board (Board): the board under test (tests/conftest.py).

    Returns:
        str: the boot id.

    Raises:
        AssertionError: the id could not be read, or came back empty.
    """
    stdout, stderr, _returncode = board.run(
        "cat /proc/sys/kernel/random/boot_id", timeout=None, check=True
    )
    output = stdout + stderr
    boot_id = "".join(output).strip()
    assert boot_id, "empty boot id -- refusing to run blind"
    return boot_id


def test_boot_profile(request, board):
    """Capture one boot profile end to end, leaving the board as it was found.

    Arms the sampler, reboots, waits out the observer window, pulls the samples and the
    matching journal, and runs the analyzer. Whatever happens, the finalizer below leaves the
    board with no copied binary, no copied unit, no enable link for it, and neither
    `/usr/local/bin` nor `/usr/local` -- no image ships either.
    """
    outdir = Path(OUTPUT_DIR)
    outdir.mkdir(parents=True, exist_ok=True)

    state = {"rebooted": False}

    def _cleanup():
        """Remove anything this run left on the board.

        Before the reboot, the driver is still on the boot this run started, so what was
        copied is removed directly. After it, the unit's own `ExecStopPost=` is expected to
        have already removed everything; this polls up to `_CLEANUP_BOUND_SECONDS` for that,
        and otherwise removes the leftovers itself, names them, and fails.
        """
        if not state["rebooted"]:
            board.run(f"systemctl disable --no-reload {_UNIT_NAME}", timeout=None)
            board.run(f"rm -f {BOARD_BINARY_PATH} {_UNIT_REMOTE}", timeout=None)
            board.run(f"rmdir {_BOARD_BIN_DIR} {_BOARD_LOCAL_DIR}", timeout=None)
            return

        deadline = time.monotonic() + _CLEANUP_BOUND_SECONDS
        leftover = []
        while True:
            board.connect()
            active_out, _stderr, _rc = board.run(f"systemctl is-active {_UNIT_NAME}", timeout=None)
            _out, _err, rc_bin = board.run(f"test -e {BOARD_BINARY_PATH}", timeout=None)
            _out, _err, rc_unit = board.run(f"test -e {_UNIT_REMOTE}", timeout=None)
            _out, _err, rc_link = board.run(f"test -e {_ENABLE_LINK}", timeout=None)
            _out, _err, rc_bin_dir = board.run(f"test -d {_BOARD_BIN_DIR}", timeout=None)
            _out, _err, rc_local_dir = board.run(f"test -d {_BOARD_LOCAL_DIR}", timeout=None)
            leftover = []
            if "".join(active_out).strip() == "active":
                leftover.append(f"{_UNIT_NAME} still active")
            if rc_bin == 0:
                leftover.append(BOARD_BINARY_PATH)
            if rc_unit == 0:
                leftover.append(_UNIT_REMOTE)
            if rc_link == 0:
                leftover.append(_ENABLE_LINK)
            if rc_bin_dir == 0:
                leftover.append(_BOARD_BIN_DIR)
            if rc_local_dir == 0:
                leftover.append(_BOARD_LOCAL_DIR)
            if not leftover:
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(_CLEANUP_POLL_SECONDS)

        board.run(f"systemctl disable --no-reload {_UNIT_NAME}", timeout=None)
        board.run(f"rm -f {BOARD_BINARY_PATH} {_UNIT_REMOTE}", timeout=None)
        board.run(f"rmdir {_BOARD_BIN_DIR} {_BOARD_LOCAL_DIR}", timeout=None)
        pytest.fail(f"board was not clean after the profile run: {', '.join(leftover)}")

    request.addfinalizer(_cleanup)

    # 1. Record the boot id.
    boot_before = _boot_id(board)

    # 2. Arm: copy the binary and the unit, then enable. scp (what board.put() shells out
    # to) does not create destination directories, so make it first.
    board.run(f"mkdir -p {_BOARD_BIN_DIR}", timeout=None, check=True)
    board.put(str(DEPLOYED_BINARY), BOARD_BINARY_PATH)
    board.run(f"chmod 0755 {BOARD_BINARY_PATH}", timeout=None, check=True)
    board.put(str(UNIT_SOURCE), "/etc/systemd/system/")
    board.run(f"systemctl daemon-reload && systemctl enable {_UNIT_NAME}", timeout=None, check=True)

    # 3. Reboot, then disconnect for the whole observer window -- a connection during it is
    # itself an instrument; see the bootprof README for the measured cost.
    try:
        board.run("systemctl reboot", timeout=10)
    except (ExecutionError, subprocess.TimeoutExpired):
        pass
    board.disconnect()
    state["rebooted"] = True
    time.sleep(WAIT_SECONDS)

    # 4. Reconnect; a failed activation counts as still the old boot.
    boot_after = None
    sample_remote = None
    for _attempt in range(_RETRY_ATTEMPTS):
        try:
            board.connect()
        except Exception:  # noqa: BLE001 -- unreachable is "still the old boot", not a failure
            time.sleep(_RETRY_INTERVAL_SECONDS)
            continue
        boot_after = _boot_id(board)
        if boot_after == boot_before:
            time.sleep(_RETRY_INTERVAL_SECONDS)
            continue
        candidate = f"/data/boot-cpu-io.{boot_after}.txt"
        _stdout, _stderr, returncode = board.run(f"test -f {candidate}", timeout=None)
        if returncode == 0:
            sample_remote = candidate
            break
        time.sleep(_RETRY_INTERVAL_SECONDS)
    assert sample_remote is not None, (
        f"no /data/boot-cpu-io.{boot_after}.txt appeared -- "
        "a sample from an earlier boot is not a profile of this one"
    )

    # 5. Fetch the samples and the matching journal.
    stem = f"boot-cpu-io.{boot_after}"
    board.get(sample_remote, str(outdir / f"{stem}.txt"))
    journal_id = boot_after.replace("-", "")
    journal_stdout, journal_stderr, journal_rc = board.run(
        f"journalctl -b {journal_id} -o short-monotonic", timeout=None
    )
    assert journal_rc == 0, (
        f"journalctl -b {journal_id} failed (rc {journal_rc}): {chr(10).join(journal_stderr)}"
    )
    journal_text = "\n".join(journal_stdout)
    assert journal_text.strip(), f"journal for boot {journal_id} is empty"
    (outdir / f"{stem}.journal.txt").write_text(journal_text + "\n")

    # 6. Analyze on the host.
    result = subprocess.run(
        ["python3", str(ANALYZER), str(outdir / f"{stem}.txt")],
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
