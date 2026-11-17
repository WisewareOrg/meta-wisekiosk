"""Target suite: with the network gone, a keyboard attached to the board gives a shell at its console."""

import hashlib
import json
import math
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import NamedTuple

import pytest

from outage import Outage

_REPO = Path(__file__).resolve().parents[2]
_SRC_DIR = Path(__file__).resolve().parent
_WORK_ROOT = _REPO / "build" / "keyboard"
_CONTAINER_WORK_ROOT = "/work/build/keyboard"
_DIR = "/tmp/test-keyboard"
_UNIT = "test-keyboard"

# `keyboard.sh`'s bounds on each wait, in seconds
_DEVICE_BOUND_SECONDS = 10
_X_OPENED_BOUND_SECONDS = 20
_CONSOLE_BOUND_SECONDS = 20
_SHELL_BOUND_SECONDS = 20
_MARKER_BOUND_SECONDS = 10
# the supplicant's leaving COMPLETED after the outage cuts, before `keyboard.sh` starts
_SUPPLICANT_LEAVES_COMPLETED_SECONDS = 5
_KEYBOARD_ARM_SECONDS = Outage.ARM_DELAY_SECONDS + _SUPPLICANT_LEAVES_COMPLETED_SECONDS
# the `sleep 1` in `keyboard.sh` between the shell prompt and the typed command
_SCRIPT_PAUSE_SECONDS = 1
_OUTAGE_MARGIN_SECONDS = 12
_RESTORE_COMMAND_TIMEOUT_SECONDS = 30
# the longest wait for X to take vt1 back after `kiosk.service` restarts
_KIOSK_RESTART_WAIT_SECONDS = 30

_USBHID = "kernel/drivers/hid/usbhid/usbhid.ko"
_HID_GENERIC = "kernel/drivers/hid/hid-generic.ko"

_EV_KEY = 1
_KEY_LEFTSHIFT = 42
_KEY_LEFTCTRL = 29
_KEY_LEFTALT = 56
_KEY_F1 = 59
_KEY_F2 = 60
_KEYS = {
    **{c: code for c, code in zip("qwertyuiop", range(16, 26))},
    **{c: code for c, code in zip("asdfghjkl", range(30, 39))},
    **{c: code for c, code in zip("zxcvbnm", range(44, 51))},
    **{c: code for c, code in zip("1234567890", range(2, 12))},
    " ": 57,
    "\n": 28,
    "/": 53,
    "-": 12,
    ".": 52,
}
_SHIFTED = {"$": "4", "(": "9", ")": "0", ">": "."}
_KEY_HOLD_US = 50_000
_KEY_GAP_US = 50_000
_CHORD_HOLD_US = 100_000

# an evemu device description: `N` the name, `I` the bus, vendor, product and version, and each
# `B` line a capability bitmap, `00` for event types and `01` for key codes
_DESC = """\
N: TST027 keyboard
I: 0003 0001 0001 0001
B: 00 0b 00 00 00 00 00 00 00
B: 01 fe ff ff ff ff ff ff ff
B: 01 ff ff ff ff ff ff ff ff
"""


def _frame(lines, t_us, keys):
    """Append the key events `keys`, as (code, value) pairs, then a SYN, all at `t_us`."""
    stamp = f"{t_us // 1_000_000}.{t_us % 1_000_000:06d}"
    for code, value in keys:
        lines.append(f"E: {stamp} {_EV_KEY:04x} {code:04x} {value}")
    lines.append(f"E: {stamp} 0000 0000 0000")


def _typed(text):
    """The evemu events that type `text`; raises on a character the tables do not cover."""
    lines = ["E: 0.000000 0000 0000 0000"]
    t_us = 0
    for char in text:
        base = _SHIFTED.get(char, char)
        if base not in _KEYS:
            raise ValueError(f"no key for {char!r}")
        shifted = char in _SHIFTED
        if shifted:
            _frame(lines, t_us, [(_KEY_LEFTSHIFT, 1)])
        _frame(lines, t_us, [(_KEYS[base], 1)])
        t_us += _KEY_HOLD_US
        _frame(lines, t_us, [(_KEYS[base], 0)])
        if shifted:
            _frame(lines, t_us, [(_KEY_LEFTSHIFT, 0)])
        t_us += _KEY_GAP_US
    return "\n".join(lines) + "\n"


def _chord(key):
    """The evemu events that hold Ctrl+Alt+`key`, then release it."""
    lines = ["E: 0.000000 0000 0000 0000"]
    _frame(lines, 0, [(_KEY_LEFTCTRL, 1), (_KEY_LEFTALT, 1), (key, 1)])
    _frame(lines, _CHORD_HOLD_US, [(key, 0), (_KEY_LEFTALT, 0), (_KEY_LEFTCTRL, 0)])
    return "\n".join(lines) + "\n"


_NONCE_BYTES = 8
_LOGIN = "root\n"


def _marker_command(nonce):
    """The command typed at the login: write the nonce, the tty and the uptime to the marker."""
    return f"echo {nonce} $(readlink /proc/self/fd/0) $(cat /proc/uptime) >{_DIR}/marker\n"


def _typing_seconds(text):
    """How long `_typed(text)` takes to replay."""
    return len(text) * (_KEY_HOLD_US + _KEY_GAP_US) / 1_000_000


# the time from `keyboard.sh`'s chord to the marker, apart from its bounds on each wait
_TYPING_SECONDS = (
    _CHORD_HOLD_US / 1_000_000
    + _typing_seconds(_LOGIN)
    + _SCRIPT_PAUSE_SECONDS
    + _typing_seconds(_marker_command("0" * 2 * _NONCE_BYTES))
)
_OUTAGE_SECONDS = math.ceil(
    _KEYBOARD_ARM_SECONDS
    + _DEVICE_BOUND_SECONDS
    + _X_OPENED_BOUND_SECONDS
    + _CONSOLE_BOUND_SECONDS
    + _SHELL_BOUND_SECONDS
    + _MARKER_BOUND_SECONDS
    + _TYPING_SECONDS
    + _OUTAGE_MARGIN_SECONDS
)


class Helpers(NamedTuple):
    """The built evemu files' directory, and what was built."""

    directory: Path
    version: str
    packages: list
    sha256: dict


@pytest.fixture(scope="module")
def helpers(request):
    """Build evemu-tools and its library through `tools/kas-run.sh`; return their `Helpers`."""
    run_dir = _WORK_ROOT / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    request.addfinalizer(lambda: shutil.rmtree(run_dir))
    subprocess.run(
        [
            str(_REPO / "tools" / "kas-run.sh"),
            "shell",
            "kiosk-zero-w.yaml",
            "-c",
            f"bash /work/tests/target_suite/evemu_tools.sh {_CONTAINER_WORK_ROOT}/{run_dir.name}",
        ],
        cwd=_REPO,
        check=True,
    )
    directory = run_dir / "helpers"
    return Helpers(
        directory,
        (run_dir / "version").read_text().strip(),
        (run_dir / "packages").read_text().split(),
        {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in sorted(path.name for path in directory.iterdir())},
    )


def _foreground_console(board):
    """The virtual terminal in the foreground, as the board's `fgconsole` prints it."""
    return board.run("fgconsole", check=True)[0][0].strip()


def _record_x(board, record_property, when):
    """Record Xorg's pid and `kiosk.service`'s restart count as the board has them."""
    record_property(f"xorg_pid_{when}", " ".join(board.run("pidof Xorg")[0]))
    record_property(
        f"kiosk_nrestarts_{when}",
        board.run("systemctl show -p NRestarts --value kiosk.service", check=True)[0][0],
    )


def _kill_tty2_login(board):
    """Kill whatever runs on tty2; `getty@.service`'s `Restart=always` brings back a fresh prompt.

    A logged-in shell outlasts a plain restart until systemd's stop timeout, so the unit is
    killed. It is not restarted: a getty that does not come back is left for the console wait to
    fail on.
    """
    board.run("systemctl kill -s KILL getty@tty2.service")


def _take_vt1(board, record_property, when):
    """Make vt1 the foreground console, restarting `kiosk.service` (whose X takes vt1) if it is not.

    A restart is recorded as `console_restored_by_restart`, with `when` as its value.
    """
    if _foreground_console(board) != "1":
        record_property("console_restored_by_restart", when)
        board.run("systemctl restart kiosk.service", check=True)
        deadline = time.monotonic() + _KIOSK_RESTART_WAIT_SECONDS
        while _foreground_console(board) != "1" and time.monotonic() < deadline:
            time.sleep(1)


def _restore_console(board, record_property):
    """Type Ctrl+Alt+F1 on a new virtual keyboard, kill tty2's login, and make vt1 foreground."""
    board.run(
        f"/bin/sh {_DIR}/keyboard.sh --chord back.events",
        check=True,
        timeout=_RESTORE_COMMAND_TIMEOUT_SECONDS,
    )
    _kill_tty2_login(board)
    _take_vt1(board, record_property, "after")
    _record_x(board, record_property, "after")
    assert _foreground_console(board) == "1", "vt1 is not the foreground console after the test"


def _record_fields(lines, kind):
    """The fields after the line kind, of each `kind` line of the keyboard record, in order."""
    return [line.split()[1:] for line in lines if line.split()[:1] == [kind]]


def test_shell_from_an_attached_keyboard(request, board, outage, helpers, tmp_path, record_property):
    """TST027 shell from an attached keyboard: with the network cut, log in at the console and run a command."""
    record_property("requirement", "TST027")
    record_property("evemu_tools_version", helpers.version)
    record_property("helper_sha256", json.dumps(helpers.sha256, sort_keys=True))
    record_property("helper_packages", " ".join(helpers.packages))
    nonce = secrets.token_hex(_NONCE_BYTES)
    command = _marker_command(nonce)
    units = f"{_UNIT}.timer {_UNIT}.service"

    request.addfinalizer(lambda: board.run(f"rm -rf {_DIR}"))
    board.run(f"systemctl stop {units}; systemctl reset-failed {units}")
    board.run(f"rm -rf {_DIR}; mkdir {_DIR}", check=True)
    _take_vt1(board, record_property, "before")
    assert _foreground_console(board) == "1", "vt1 is not the foreground console before the test"
    outage.wait_boot_complete()
    _kill_tty2_login(board)

    boot_id = board.run("cat /proc/sys/kernel/random/boot_id", check=True)[0][0]
    builtin = board.run("cat /lib/modules/$(uname -r)/modules.builtin", check=True)[0]
    hid_drivers = [entry for entry in builtin if entry in (_USBHID, _HID_GENERIC)]
    record_property("modules_builtin_hid", "\n".join(hid_drivers))
    assert {_USBHID, _HID_GENERIC} <= set(builtin), (
        "the USB keyboard drivers are not built in: CONFIG_USB_HID=y (usbhid.ko) and "
        "CONFIG_HID_GENERIC=y (hid-generic.ko) must both be in modules.builtin"
    )
    _record_x(board, record_property, "before")

    uinput_loaded = board.run("test -d /sys/module/uinput")[2] == 0
    board.run("modprobe uinput", check=True)
    if not uinput_loaded:
        request.addfinalizer(lambda: board.run("rmmod uinput", check=True))

    sources = tmp_path / "events"
    sources.mkdir()
    (sources / "keyboard.desc").write_text(_DESC)
    (sources / "chord.events").write_text(_chord(_KEY_F2))
    (sources / "login.events").write_text(_typed(_LOGIN))
    (sources / "command.events").write_text(_typed(command))
    (sources / "back.events").write_text(_chord(_KEY_F1))
    for name in sorted(path.name for path in sources.iterdir()):
        board.put(str(sources / name), f"{_DIR}/{name}")
    for name in helpers.sha256:
        board.put(str(helpers.directory / name), f"{_DIR}/{name}")
    board.put(str(_SRC_DIR / "keyboard.sh"), f"{_DIR}/keyboard.sh")
    board.run("chmod 0755 " + " ".join(f"{_DIR}/{name}" for name in helpers.sha256), check=True)

    request.addfinalizer(lambda: _restore_console(board, record_property))
    request.addfinalizer(
        lambda: board.run(f"systemctl stop {units}; systemctl reset-failed {units}")
    )

    bounds = " ".join(
        str(bound)
        for bound in (
            _DEVICE_BOUND_SECONDS,
            _X_OPENED_BOUND_SECONDS,
            _CONSOLE_BOUND_SECONDS,
            _SHELL_BOUND_SECONDS,
            _MARKER_BOUND_SECONDS,
        )
    )
    board.run(
        f"systemd-run --unit={_UNIT} --on-active={_KEYBOARD_ARM_SECONDS} "
        f"--timer-property=AccuracySec=100ms /bin/sh {_DIR}/keyboard.sh {bounds}",
        check=True,
    )
    outage.arm(request, _OUTAGE_SECONDS)

    # two seconds past the outage's end, so the network is back before the reconnect
    time.sleep(Outage.ARM_DELAY_SECONDS + _OUTAGE_SECONDS + 2)
    board.reconnect()

    boot_id_after = board.run("cat /proc/sys/kernel/random/boot_id", check=True)[0][0]
    keyboard_record = board.run(f"cat {_DIR}/record 2>/dev/null || true", check=True)[0]
    marker = board.run(f"cat {_DIR}/marker 2>/dev/null || true", check=True)[0]
    outage_record = outage.record_lines()
    cut = outage.field(outage_record, "cut")
    t0 = outage.field(outage_record, "t0")
    prompts = _record_fields(keyboard_record, "prompt")
    after_login = prompts[0][0] if prompts else "not reached"

    record_property("outage_s", _OUTAGE_SECONDS)
    record_property("keyboard_record", "\n".join(keyboard_record))
    record_property("after_login", after_login)
    record_property("marker", "\n".join(marker))
    record_property("cut_uptime_s", cut)
    record_property("t0_uptime_s", t0)

    reached = {fields[0] for fields in _record_fields(keyboard_record, "phase")}

    def journal():
        stdout, _stderr, _rc = board.run(f"journalctl -u {_UNIT} -o cat --no-pager")
        return "\n".join(stdout)

    assert boot_id_after == boot_id, (
        "the board restarted during the outage (outage.sh's give-up), so the marker in /tmp is gone"
    )
    assert "device" in reached, (
        "the virtual keyboard was not created (the test's own setup, not the appliance): "
        f"{journal()}"
    )
    assert "x_opened" in reached, f"X never opened the attached keyboard: {journal()}"
    assert "console" in reached, f"Ctrl+Alt+F2 brought no login prompt on tty2: {journal()}"
    assert "shell" in reached, f"logging in as root on tty2 gave no shell (after login: {after_login})"
    fields = marker[0].split() if marker else []
    assert fields[:1] == [nonce], f"the typed command did not run: marker {marker!r}"
    assert fields[1:2] == ["/dev/tty2"], f"the command ran on {fields[1:2]}, not at the tty2 login"
    assert cut is not None and t0 is not None, f"the outage record has no cut and t0: {outage_record}"
    assert cut < float(fields[2]) < t0, (
        f"the command ran with the network up: it ran at {fields[2]}, the outage was {cut} to {t0}"
    )
