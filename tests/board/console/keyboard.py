"""The evemu keyboard `keyboard.sh` attaches to the board and types into its consoles."""

from pathlib import Path
from typing import NamedTuple

from board.virtual_input import VirtualInput

_SRC_DIR = Path(__file__).resolve().parents[2] / "target_suite"
_DIR = "/tmp/test-keyboard"
_UNIT = "test-keyboard"
_RESTORE_COMMAND_TIMEOUT_SECONDS = 30

_EV_KEY = 1
_KEY_LEFTSHIFT = 42
_KEY_LEFTCTRL = 29
_KEY_LEFTALT = 56
_KEY_F1 = 59
_KEY_F2 = 60
_KEYS = {
    **{c: code for c, code in zip("qwertyuiop", range(16, 26), strict=False)},
    **{c: code for c, code in zip("asdfghjkl", range(30, 39), strict=False)},
    **{c: code for c, code in zip("zxcvbnm", range(44, 51), strict=False)},
    **{c: code for c, code in zip("1234567890", range(2, 12), strict=False)},
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
# the `sleep 1` in `keyboard.sh` between the shell prompt and the typed command
_SCRIPT_PAUSE_SECONDS = 1
_LOGIN = "root\n"

# an evemu device description: `N` the name, `I` the bus, vendor, product and version, and each
# `B` line a capability bitmap, `00` for event types and `01` for key codes
_DESC = """\
N: TST027 keyboard
I: 0003 0001 0001 0001
B: 00 0b 00 00 00 00 00 00 00
B: 01 fe ff ff ff ff ff ff ff
B: 01 ff ff ff ff ff ff ff ff
"""


class TypedMarker(NamedTuple):
    """The marker the typed command writes.

    Attributes:
        word: what it was typed to write first; empty if it wrote nothing.
        terminal: the terminal it ran on; empty if it wrote nothing.
        uptime: the board's uptime when it ran; None if it wrote nothing.
    """

    word: str = ""
    terminal: str = ""
    uptime: float | None = None


class Keyboard(VirtualInput):
    """A virtual keyboard `keyboard.sh` attaches to the board through uinput and types into the consoles.

    Attributes:
        WORD_CHARS: how long the word the typed command writes is.
    """

    WORD_CHARS = 16

    @staticmethod
    def typing_seconds() -> float:
        """How long the typing takes from `keyboard.sh`'s chord to the marker, apart from its bounds on each wait.

        Returns:
            The seconds.
        """
        return (
            _CHORD_HOLD_US / 1_000_000
            + Keyboard._typing_seconds(_LOGIN)
            + _SCRIPT_PAUSE_SECONDS
            + Keyboard._typing_seconds(Keyboard._marker_command("0" * Keyboard.WORD_CHARS))
        )

    def install(self, nonce: str) -> None:
        """Put the keyboard on the board until the test ends: `keyboard.sh`, and the events it plays.

        The events type the login, then a command that writes `nonce`, the terminal and the uptime to
        the marker.

        Args:
            nonce: what the typed command writes first to the marker.
        """
        self._put(
            _DIR,
            {
                "keyboard.sh": (_SRC_DIR / "keyboard.sh").read_text(),
                "keyboard.desc": _DESC,
                "chord.events": self._chord_events(_KEY_F2),
                "login.events": self._typing_events(_LOGIN),
                "command.events": self._typing_events(self._marker_command(nonce)),
                "back.events": self._chord_events(_KEY_F1),
            },
        )

    def type_after(self, delay: float, bounds: tuple[float, ...]) -> None:
        """Have a board-side timer run `keyboard.sh` in `delay` seconds, until the test ends.

        Args:
            delay: seconds from now to the start.
            bounds: `keyboard.sh`'s bound on each phase's wait, in its order: device, browser opened,
                console, shell, marker.
        """
        self._board.run_later(_UNIT, delay, f"/bin/sh {_DIR}/keyboard.sh {' '.join(str(b) for b in bounds)}")

    def press_vt1_chord(self) -> None:
        """Press Ctrl+Alt+F1 on a new virtual keyboard."""
        self._board.run(
            f"/bin/sh {_DIR}/keyboard.sh --chord back.events", check=True, timeout=_RESTORE_COMMAND_TIMEOUT_SECONDS
        )

    def typed_record(self) -> tuple[list[str], set[str]]:
        """Read what `keyboard.sh` recorded of its phases.

        Returns:
            The record's lines, then the phases it reached.
        """
        lines = self._board.run(f"cat {_DIR}/record 2>/dev/null || true", check=True).stdout
        return lines, {line.split()[1] for line in lines if line.split()[:1] == ["phase"]}

    def typed_marker(self) -> TypedMarker:
        """Read the marker the typed command wrote.

        Returns:
            The marker; empty if the command wrote none.
        """
        lines = self._board.run(f"cat {_DIR}/marker 2>/dev/null || true", check=True).stdout
        fields = lines[0].split() if lines else []
        return TypedMarker(fields[0], fields[1], float(fields[2])) if len(fields) >= 3 else TypedMarker()

    def typed_panel(self) -> str:
        """Read what `keyboard.sh` kept of the panel when the typed command had run.

        Returns:
            The display driver's state; empty if it kept none.
        """
        return self._board.run(f"cat {_DIR}/panel 2>/dev/null || true", check=True).text

    def journal(self) -> str:
        """Read `keyboard.sh`'s journal, from its timer unit.

        Returns:
            The journal's lines, joined.
        """
        return "\n".join(self._board.run(f"journalctl -u {_UNIT} -o cat --no-pager").stdout)

    @staticmethod
    def _marker_command(nonce: str) -> str:
        """The command typed at the login: write the nonce, the tty and the uptime to the marker.

        Args:
            nonce: what the command writes first.

        Returns:
            The command line, with its newline.
        """
        return f"echo {nonce} $(readlink /proc/self/fd/0) $(cat /proc/uptime) >{_DIR}/marker\n"

    @staticmethod
    def _typing_seconds(text: str) -> float:
        """How long typing `text` takes to replay.

        Args:
            text: the text typed.

        Returns:
            The seconds.
        """
        return len(text) * (_KEY_HOLD_US + _KEY_GAP_US) / 1_000_000

    @staticmethod
    def _append_key_frame(lines: list[str], t_us: int, keys: list[tuple[int, int]]) -> None:
        """Append the key events `keys`, as (code, value) pairs, then a SYN, all at `t_us`.

        Args:
            lines: the events so far.
            t_us: the frame's time, in microseconds.
            keys: the key codes and values.
        """
        stamp = f"{t_us // 1_000_000}.{t_us % 1_000_000:06d}"
        for code, value in keys:
            lines.append(f"E: {stamp} {_EV_KEY:04x} {code:04x} {value}")
        lines.append(f"E: {stamp} 0000 0000 0000")

    @staticmethod
    def _typing_events(text: str) -> str:
        """The evemu events that type `text`.

        Args:
            text: the text to type.

        Returns:
            The events file's text.

        Raises:
            ValueError: a character the key tables do not cover.
        """
        lines = ["E: 0.000000 0000 0000 0000"]
        t_us = 0
        for char in text:
            base = _SHIFTED.get(char, char)
            if base not in _KEYS:
                raise ValueError(f"no key for {char!r}")
            shifted = char in _SHIFTED
            if shifted:
                Keyboard._append_key_frame(lines, t_us, [(_KEY_LEFTSHIFT, 1)])
            Keyboard._append_key_frame(lines, t_us, [(_KEYS[base], 1)])
            t_us += _KEY_HOLD_US
            Keyboard._append_key_frame(lines, t_us, [(_KEYS[base], 0)])
            if shifted:
                Keyboard._append_key_frame(lines, t_us, [(_KEY_LEFTSHIFT, 0)])
            t_us += _KEY_GAP_US
        return "\n".join(lines) + "\n"

    @staticmethod
    def _chord_events(key: int) -> str:
        """The evemu events that hold Ctrl+Alt+`key`, then release it.

        Args:
            key: the key code held with Ctrl and Alt.

        Returns:
            The events file's text.
        """
        lines = ["E: 0.000000 0000 0000 0000"]
        Keyboard._append_key_frame(lines, 0, [(_KEY_LEFTCTRL, 1), (_KEY_LEFTALT, 1), (key, 1)])
        Keyboard._append_key_frame(lines, _CHORD_HOLD_US, [(key, 0), (_KEY_LEFTALT, 0), (_KEY_LEFTCTRL, 0)])
        return "\n".join(lines) + "\n"
