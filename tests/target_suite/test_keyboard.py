"""Target suite: with the network gone, a keyboard attached to the board gives a shell at its console."""

import contextlib
import hashlib
import json
import math
import secrets
import time
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import pytest
from board import Board
from container_dir import ContainerDir
from outage import Outage
from record import Record

_SRC_DIR = Path(__file__).resolve().parent
_DIR = "/tmp/test-keyboard"
_UNIT = "test-keyboard"
_JOURNAL_CMD = f"journalctl -u {_UNIT} -o cat --no-pager"

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
    **{c: code for c, code in zip("qwertyuiop", range(16, 26), strict=True)},
    **{c: code for c, code in zip("asdfghjkl", range(30, 39), strict=True)},
    **{c: code for c, code in zip("zxcvbnm", range(44, 51), strict=True)},
    **{c: code for c, code in zip("1234567890", range(2, 12), strict=True)},
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


def _frame(lines: list[str], t_us: int, keys: list[tuple[int, int]]) -> None:
    """Append the key events `keys`, as (code, value) pairs, then a SYN, all at `t_us`.

    Args:
        lines: the evemu event lines, appended to in place.
        t_us: the events' time, in microseconds.
        keys: the (key code, value) pairs.
    """
    stamp = f"{t_us // 1_000_000}.{t_us % 1_000_000:06d}"
    for code, value in keys:
        lines.append(f"E: {stamp} {_EV_KEY:04x} {code:04x} {value}")
    lines.append(f"E: {stamp} 0000 0000 0000")


def _typed(text: str) -> str:
    """The evemu events that type `text`.

    Args:
        text: what to type.

    Returns:
        The events, one per line.

    Raises:
        ValueError: a character has no key in the tables.
    """
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


def _chord(key: int) -> str:
    """The evemu events that hold Ctrl+Alt+`key`, then release it.

    Args:
        key: the key code held with Ctrl and Alt.

    Returns:
        The events, one per line.
    """
    lines = ["E: 0.000000 0000 0000 0000"]
    _frame(lines, 0, [(_KEY_LEFTCTRL, 1), (_KEY_LEFTALT, 1), (key, 1)])
    _frame(lines, _CHORD_HOLD_US, [(key, 0), (_KEY_LEFTALT, 0), (_KEY_LEFTCTRL, 0)])
    return "\n".join(lines) + "\n"


_NONCE_BYTES = 8
_LOGIN = "root\n"


def _marker_command(nonce: str) -> str:
    """The command typed at the login: write the nonce, the tty and the uptime to the marker.

    Args:
        nonce: this run's nonce.

    Returns:
        The command line, with its newline.
    """
    return f"echo {nonce} $(readlink /proc/self/fd/0) $(cat /proc/uptime) >{_DIR}/marker\n"


def _typing_seconds(text: str) -> float:
    """How long `_typed(text)` takes to replay.

    Args:
        text: what is typed.

    Returns:
        The seconds.
    """
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
    """The built evemu files' directory, and what was built.

    Attributes:
        directory: where the built files are.
        version: the evemu-tools version.
        packages: the packages built.
        sha256: each built file's sha256, by name.
    """

    directory: Path
    version: str
    packages: list
    sha256: dict


@pytest.fixture(scope="module")
def helpers() -> Iterator[Helpers]:
    """Build evemu-tools and its library through `tools/kas-run.sh`; return their `Helpers`.

    Yields:
        Helpers: The built files' directory, the version, the packages and each file's sha256; the build
        directory is removed once the module ends.
    """
    with contextlib.ExitStack() as cleanup:
        work = ContainerDir(cleanup)
        work.run("evemu_tools.sh")
        directory = work.path / "helpers"
        yield Helpers(
            directory,
            (work.path / "version").read_text().strip(),
            (work.path / "packages").read_text().split(),
            {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(directory.iterdir())},
        )


class _Console:
    """The board's virtual consoles as the test leaves them: foreground, X's pid, tty2's login."""

    def __init__(self, board: Board, record: Record) -> None:
        """Bind to the board.

        Args:
            board: the board under test.
            record: records what the console steps measure.
        """
        self._board = board
        self._record = record

    def foreground(self) -> str:
        """The virtual terminal in the foreground, as the board's `fgconsole` prints it.

        Returns:
            The terminal's number.
        """
        return self._board.read("fgconsole")

    def take_vt1(self, when: str) -> None:
        """Make vt1 the foreground console, restarting `kiosk.service` (whose X takes vt1) if it is not.

        A restart is recorded as `console_restored_by_restart`, with `when` as its value.

        Args:
            when: `before` or `after`, as the restart is recorded.
        """
        if self.foreground() != "1":
            self._record(console_restored_by_restart=when)
            self._board.run("systemctl restart kiosk.service", check=True)
            self._board.wait_until(self.foreground, lambda console: console == "1", _KIOSK_RESTART_WAIT_SECONDS)

    def kill_tty2_login(self) -> None:
        """Kill whatever runs on tty2; `getty@.service`'s `Restart=always` brings back a fresh prompt.

        A logged-in shell outlasts a plain restart until systemd's stop timeout, so the unit is
        killed. It is not restarted: a getty that does not come back is left for the console wait to
        fail on.
        """
        self._board.run("systemctl kill -s KILL getty@tty2.service")

    def record_x(self, when: str) -> None:
        """Record Xorg's pid and `kiosk.service`'s restart count as the board has them.

        Args:
            when: `before` or `after`, as the records are named.
        """
        self._record(
            **{
                f"xorg_pid_{when}": " ".join(self._board.run("pidof Xorg")[0]),
                f"kiosk_nrestarts_{when}": self._board.read("systemctl show -p NRestarts --value kiosk.service"),
            }
        )

    def restore(self) -> None:
        """Type Ctrl+Alt+F1 on a new virtual keyboard, kill tty2's login, and make vt1 foreground."""
        self._board.run(
            f"/bin/sh {_DIR}/keyboard.sh --chord back.events",
            check=True,
            timeout=_RESTORE_COMMAND_TIMEOUT_SECONDS,
        )
        self.kill_tty2_login()
        self.take_vt1("after")
        self.record_x("after")
        assert self.foreground() == "1", "vt1 is not the foreground console after the test"


def _record_fields(lines: list[str], kind: str) -> list[list[str]]:
    """The fields after the line kind, of each `kind` line of the keyboard record, in order.

    Args:
        lines: the keyboard record's lines.
        kind: the first word of the lines wanted.

    Returns:
        One list of fields per matching line.
    """
    return [line.split()[1:] for line in lines if line.split()[:1] == [kind]]


class TestKeyboard:
    """With the network gone, a keyboard attached to the board gives a shell at its console."""

    @pytest.fixture(autouse=True)
    def setup(self, board: Board, record: Record, helpers: Helpers, tmp_path: Path) -> Iterator[None]:
        """Keep what every test here uses, and undo what each test changed once it ends.

        Args:
            board: the board under test.
            record: the test's record.
            helpers: the evemu tools built for the module.
            tmp_path: where the event files are written before they are put on the board.

        Yields:
            None: the test runs, then `self.cleanup` undoes its changes, last first.
        """
        self.board = board
        self.record = record
        self.helpers = helpers
        self.tmp_path = tmp_path
        with contextlib.ExitStack() as self.cleanup:
            yield

    def test_shell_from_an_attached_keyboard(self) -> None:
        """TST027 shell from an attached keyboard: with the network cut, log in at the console and run a command."""
        self.record(requirement="TST027")
        self.record(
            evemu_tools_version=self.helpers.version,
            helper_sha256=json.dumps(self.helpers.sha256, sort_keys=True),
            helper_packages=" ".join(self.helpers.packages),
        )
        nonce = secrets.token_hex(_NONCE_BYTES)
        command = _marker_command(nonce)
        console = _Console(self.board, self.record)

        self.cleanup.callback(self.board.run, f"rm -rf {_DIR}")
        self.board.run(f"rm -rf {_DIR}; mkdir {_DIR}", check=True)
        console.take_vt1("before")
        assert console.foreground() == "1", "vt1 is not the foreground console before the test"
        outage = Outage(self.board, self.cleanup)
        outage.wait_boot_complete()
        console.kill_tty2_login()

        boot_id = self.board.read(self.board.BOOT_ID_CMD)
        builtin = self.board.run("cat /lib/modules/$(uname -r)/modules.builtin", check=True)[0]
        hid_drivers = [entry for entry in builtin if entry in (_USBHID, _HID_GENERIC)]
        self.record(modules_builtin_hid="\n".join(hid_drivers))
        assert {_USBHID, _HID_GENERIC} <= set(builtin), (
            "the USB keyboard drivers are not built in: CONFIG_USB_HID=y (usbhid.ko) and "
            "CONFIG_HID_GENERIC=y (hid-generic.ko) must both be in modules.builtin"
        )
        console.record_x("before")

        uinput_loaded = self.board.run("test -d /sys/module/uinput")[2] == 0
        self.board.run("modprobe uinput", check=True)
        if not uinput_loaded:
            self.cleanup.callback(self.board.run, "rmmod uinput", check=True)

        sources = self.tmp_path / "events"
        sources.mkdir()
        (sources / "keyboard.desc").write_text(_DESC)
        (sources / "chord.events").write_text(_chord(_KEY_F2))
        (sources / "login.events").write_text(_typed(_LOGIN))
        (sources / "command.events").write_text(_typed(command))
        (sources / "back.events").write_text(_chord(_KEY_F1))
        for name in sorted(path.name for path in sources.iterdir()):
            self.board.put(str(sources / name), f"{_DIR}/{name}")
        for name in self.helpers.sha256:
            self.board.put(str(self.helpers.directory / name), f"{_DIR}/{name}")
        self.board.put(str(_SRC_DIR / "keyboard.sh"), f"{_DIR}/keyboard.sh")
        self.board.run("chmod 0755 " + " ".join(f"{_DIR}/{name}" for name in self.helpers.sha256), check=True)

        self.cleanup.callback(console.restore)

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
        self.board.run_later(self.cleanup, _UNIT, _KEYBOARD_ARM_SECONDS, f"/bin/sh {_DIR}/keyboard.sh {bounds}")
        outage.arm(_OUTAGE_SECONDS)

        # two seconds past the outage's end, so `reconnect` starts retrying only once the network is un-pinned
        time.sleep(Outage.ARM_DELAY_SECONDS + _OUTAGE_SECONDS + 2)
        self.board.reconnect()

        boot_id_after = self.board.read(self.board.BOOT_ID_CMD)
        keyboard_record = self.board.run(f"cat {_DIR}/record 2>/dev/null || true", check=True)[0]
        marker = self.board.run(f"cat {_DIR}/marker 2>/dev/null || true", check=True)[0]
        outage_record = outage.record_lines()
        cut = outage.field(outage_record, "cut")
        t0 = outage.field(outage_record, "t0")
        prompts = _record_fields(keyboard_record, "prompt")
        after_login = prompts[0][0] if prompts else "not reached"

        self.record(
            outage_s=_OUTAGE_SECONDS,
            keyboard_record="\n".join(keyboard_record),
            after_login=after_login,
            marker="\n".join(marker),
            cut_uptime_s=cut,
            t0_uptime_s=t0,
        )

        reached = {fields[0] for fields in _record_fields(keyboard_record, "phase")}

        assert boot_id_after == boot_id, (
            "the board restarted during the outage (outage.sh's give-up), so the marker in /tmp is gone"
        )
        assert "device" in reached, (
            "the virtual keyboard was not created (the test's own setup, not the appliance): "
            f"{self.board.read(_JOURNAL_CMD)}"
        )
        assert "x_opened" in reached, f"X never opened the attached keyboard: {self.board.read(_JOURNAL_CMD)}"
        assert "console" in reached, f"Ctrl+Alt+F2 brought no login prompt on tty2: {self.board.read(_JOURNAL_CMD)}"
        assert "shell" in reached, f"logging in as root on tty2 gave no shell (after login: {after_login})"
        fields = marker[0].split() if marker else []
        assert fields[:1] == [nonce], f"the typed command did not run: marker {marker!r}"
        assert fields[1:2] == ["/dev/tty2"], f"the command ran on {fields[1:2]}, not at the tty2 login"
        assert cut is not None and t0 is not None, f"the outage record has no cut and t0: {outage_record}"
        assert cut < float(fields[2]) < t0, (
            f"the command ran with the network up: it ran at {fields[2]}, the outage was {cut} to {t0}"
        )
