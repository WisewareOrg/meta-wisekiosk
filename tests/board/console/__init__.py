"""The board's consoles, as a keyboard attached at the input layer reaches them with the network gone."""

import math
import secrets
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from board.console.keyboard import Keyboard, TypedMarker
from board.network.outage import Outage
from board.part import Part, invalid_if
from board.screen import Plane

if TYPE_CHECKING:
    from board import Board

# `keyboard.sh`'s bounds on each wait, in its order: device, browser opened, console, shell, marker
_BOUNDS_SECONDS = (10, 20, 20, 20, 10)
# the supplicant's leaving COMPLETED after the outage cuts, before `keyboard.sh` starts
_KEYBOARD_START_SECONDS = Outage.CUT_DELAY_SECONDS + 5
# the outage outlasts every wait and the typing, with a margin for the board's own pace
_OUTAGE_MARGIN_SECONDS = 12
_OUTAGE_SECONDS = math.ceil(
    _KEYBOARD_START_SECONDS + sum(_BOUNDS_SECONDS) + Keyboard.typing_seconds() + _OUTAGE_MARGIN_SECONDS
)


class Typed(NamedTuple):
    """A command typed at the console, what it left, and what the panel showed once the outage had ended.

    Attributes:
        word: what the command was typed to write first.
        marker: what the command wrote; empty if it did not run.
        progress: `keyboard.sh`'s log of how far it got.
        panel: the planes the panel was showing once the outage had ended.
        panel_then: the planes the panel was showing when the command had run; empty if none were kept.
        vt_then: the foreground console when the command had run; empty if none was kept.
    """

    word: str
    marker: TypedMarker
    progress: str
    panel: list[Plane]
    panel_then: list[Plane]
    vt_then: str


class Console(Part):
    """The board's virtual terminals: the page on vt1, and a login prompt on tty2."""

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        super().__init__(board)
        self._keyboard = Keyboard(board)

    def type_offline(self) -> Typed:
        """With the network cut off, attach a keyboard at the input layer, log in at tty2, and type a command.

        The command writes a random word, the terminal and the uptime to a marker. Before the outage, vt1 is
        brought forward and tty2 given a fresh login; the panel's planes and the foreground console are
        kept when the command has run, and the planes are read again once the outage has ended, before
        anything puts the page back. When the test ends, vt1 is put back in front and the browser is
        waited for on the panel, whatever the chord did. The check is invalid if the keyboard was not
        created, the board restarted during the outage (taking the evidence in /tmp with it), or the
        outage's record does not show the board cut off when the command ran.

        Returns:
            The command, what it left, and the panel's planes after the outage.
        """
        word = secrets.token_hex(Keyboard.WORD_CHARS // 2)
        outage = self._board.network.outage
        self._bring_vt1_forward()
        outage.wait_boot_complete()
        self._kill_tty2_login()
        boot_id = self._board.boot_id()
        events = tempfile.TemporaryDirectory()
        self._board.cleanup.enter_context(events)
        self._keyboard.install(self._board.fixture("evemu_helpers"), word, Path(events.name))
        self._board.cleanup.callback(self._board.seconds_until, self._browser_is_on_the_panel)
        self._board.cleanup.callback(self._bring_vt1_forward)
        self._board.cleanup.callback(self._kill_tty2_login)
        self._board.cleanup.callback(self._keyboard.press_vt1_chord)
        self._keyboard.type_after(_KEYBOARD_START_SECONDS, _BOUNDS_SECONDS)
        outage.schedule(_OUTAGE_SECONDS)
        time.sleep(Outage.CUT_DELAY_SECONDS + _OUTAGE_SECONDS + 2)
        self._board.reconnect()
        with invalid_if("the board restarted during the outage, and the evidence in /tmp with it"):
            assert self._board.boot_id() == boot_id
        panel = self._board.screen.planes()
        lines, phases = self._keyboard.typed_record()
        with invalid_if(f"the virtual keyboard was not created: {self._keyboard.journal()}"):
            assert "device" in phases
        marker = self._keyboard.typed_marker()
        if marker.uptime is not None:
            record = outage.read_record()
            with invalid_if(f"the record does not show the board cut off when the command ran: {record.lines}"):
                assert record.offline_at(marker.uptime)
        state, vt_then = self._keyboard.typed_panel()
        return Typed(word, marker, "\n".join(lines), panel, self._board.screen.planes(state), vt_then)

    def _foreground_vt(self) -> str:
        """Read the virtual terminal in the foreground.

        Returns:
            Its number, as `fgconsole` prints it; empty if it could not be read.
        """
        fgconsole = self._board.run("fgconsole")
        return fgconsole.text if fgconsole.returncode == 0 else ""

    def _bring_vt1_forward(self) -> None:
        """Make vt1 the foreground terminal, switching to it if it is not."""
        if not self._vt1_is_in_front():
            self._board.run("chvt 1", check=True)
            self._board.seconds_until(self._vt1_is_in_front)

    def _vt1_is_in_front(self) -> bool:
        """Whether vt1 is the foreground terminal.

        Returns:
            True if it is.
        """
        return self._foreground_vt() == "1"

    def _browser_is_on_the_panel(self) -> bool:
        """Whether the browser owns the only plane on the panel.

        Returns:
            True if it does.
        """
        return [plane.allocated_by for plane in self._board.screen.planes()] == ["kiosk-browser"]

    def _kill_tty2_login(self) -> None:
        """Kill whatever runs on tty2; `getty@.service`'s `Restart=always` brings back a fresh prompt.

        A logged-in shell outlasts a plain restart until systemd's stop timeout, so the unit is killed.
        """
        self._board.run("systemctl kill -s KILL getty@tty2.service")
