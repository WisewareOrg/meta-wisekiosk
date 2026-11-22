"""Target suite: with the network gone, a keyboard attached to the board gives a shell at its console."""

import json
import math
import secrets
import time
from pathlib import Path

from board.console.keyboard import Keyboard
from board.network.outage import Outage
from board_test import BoardTest
from evemu_helpers import EvemuHelpers

# `keyboard.sh`'s bounds on each wait, in seconds
_DEVICE_BOUND_SECONDS = 10
_X_OPENED_BOUND_SECONDS = 20
_CONSOLE_BOUND_SECONDS = 20
_SHELL_BOUND_SECONDS = 20
_MARKER_BOUND_SECONDS = 10
# the supplicant's leaving COMPLETED after the outage cuts, before `keyboard.sh` starts
_SUPPLICANT_LEAVES_COMPLETED_SECONDS = 5
_KEYBOARD_START_SECONDS = Outage.CUT_DELAY_SECONDS + _SUPPLICANT_LEAVES_COMPLETED_SECONDS
_OUTAGE_MARGIN_SECONDS = 12
_OUTAGE_SECONDS = math.ceil(
    _KEYBOARD_START_SECONDS
    + _DEVICE_BOUND_SECONDS
    + _X_OPENED_BOUND_SECONDS
    + _CONSOLE_BOUND_SECONDS
    + _SHELL_BOUND_SECONDS
    + _MARKER_BOUND_SECONDS
    + Keyboard.typing_seconds()
    + _OUTAGE_MARGIN_SECONDS
)

_USBHID = "kernel/drivers/hid/usbhid/usbhid.ko"
_HID_GENERIC = "kernel/drivers/hid/hid-generic.ko"


class TestKeyboard(BoardTest):
    """With the network gone, a keyboard attached to the board gives a shell at its console."""

    def test_shell_from_an_attached_keyboard(self, evemu_helpers: EvemuHelpers, tmp_path: Path) -> None:
        """TST027 shell from an attached keyboard: with the network cut, log in at the console and run a command.

        Args:
            evemu_helpers: the evemu tools, built for the board.
            tmp_path: where the keyboard's event files are written before they are put on the board.
        """
        self.record(requirement="TST027")
        self.record(
            evemu_tools_version=evemu_helpers.version,
            helper_sha256=json.dumps(evemu_helpers.sha256, sort_keys=True),
            helper_packages=" ".join(evemu_helpers.packages),
        )
        terminals = self.board.console.terminals
        keyboard = self.board.console.keyboard
        outage = self.board.network.outage
        nonce = secrets.token_hex(Keyboard.NONCE_BYTES)
        terminals.bring_vt1_forward("before", self.record)
        assert terminals.foreground_vt() == "1", "vt1 is not the foreground console before the test"
        outage.wait_boot_complete()
        terminals.kill_tty2_login()
        boot_id = self.board.system.kernel.boot_id()
        builtin = self.board.system.kernel.builtin_modules()
        self.record(modules_builtin_hid="\n".join(entry for entry in builtin if entry in (_USBHID, _HID_GENERIC)))
        assert {_USBHID, _HID_GENERIC} <= set(builtin), (
            "the USB keyboard drivers are not built in: CONFIG_USB_HID=y (usbhid.ko) and "
            "CONFIG_HID_GENERIC=y (hid-generic.ko) must both be in modules.builtin"
        )
        terminals.x_server_on_vt1("before", self.record)
        keyboard.install(evemu_helpers, nonce, tmp_path)
        terminals.restore_after_test(self.record)
        keyboard.type_after(
            _KEYBOARD_START_SECONDS,
            (
                _DEVICE_BOUND_SECONDS,
                _X_OPENED_BOUND_SECONDS,
                _CONSOLE_BOUND_SECONDS,
                _SHELL_BOUND_SECONDS,
                _MARKER_BOUND_SECONDS,
            ),
        )

        outage.schedule(_OUTAGE_SECONDS)
        # two seconds past the outage's end, so `reconnect` starts retrying only once the network is un-pinned
        time.sleep(Outage.CUT_DELAY_SECONDS + _OUTAGE_SECONDS + 2)
        self.board.reconnect()

        boot_id_after = self.board.system.kernel.boot_id()
        typed = keyboard.typed_record()
        marker = keyboard.typed_marker()
        outage_record = outage.read_record()
        self.record(
            outage_s=_OUTAGE_SECONDS,
            keyboard_record="\n".join(typed.lines),
            after_login=typed.after_login,
            marker="\n".join(marker.lines),
            cut_uptime_s=outage_record.cut,
            t0_uptime_s=outage_record.restored,
        )
        assert boot_id_after == boot_id, (
            "the board restarted during the outage (outage.sh's give-up), so the marker in /tmp is gone"
        )
        assert "device" in typed.phases, (
            f"the virtual keyboard was not created (the test's own setup, not the appliance): {keyboard.journal()}"
        )
        assert "x_opened" in typed.phases, f"X never opened the attached keyboard: {keyboard.journal()}"
        assert "console" in typed.phases, f"Ctrl+Alt+F2 brought no login prompt on tty2: {keyboard.journal()}"
        assert "shell" in typed.phases, f"logging in as root on tty2 gave no shell (after login: {typed.after_login})"
        assert marker.fields[:1] == [nonce], f"the typed command did not run: marker {marker.lines!r}"
        assert marker.fields[1:2] == ["/dev/tty2"], f"the command ran on {marker.fields[1:2]}, not at the tty2 login"
        assert outage_record.cut is not None and outage_record.restored is not None, (
            f"the outage record has no cut and t0: {outage_record.lines}"
        )
        assert outage_record.cut < float(marker.fields[2]) < outage_record.restored, (
            f"the command ran with the network up: it ran at {marker.fields[2]}, "
            f"the outage was {outage_record.cut} to {outage_record.restored}"
        )
