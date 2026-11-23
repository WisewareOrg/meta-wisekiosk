"""The board's consoles, as a keyboard attached at the input layer reaches them with the network gone."""

import math
import secrets
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from board.console.keyboard import Keyboard
from board.network.outage import Outage
from board.part import Part, invalid_if

if TYPE_CHECKING:
    from board import Board

# `keyboard.sh`'s bounds on each wait, in its order: device, X opened, console, shell, marker
_BOUNDS_SECONDS = (10, 20, 20, 20, 10)
# the supplicant's leaving COMPLETED after the outage cuts, before `keyboard.sh` starts
_KEYBOARD_START_SECONDS = Outage.CUT_DELAY_SECONDS + 5
_OUTAGE_SECONDS = math.ceil(_KEYBOARD_START_SECONDS + sum(_BOUNDS_SECONDS) + Keyboard.typing_seconds() + 12)
# the longest wait for X to take vt1 back after `kiosk.service` restarts
_KIOSK_RESTART_WAIT_SECONDS = 30


class Typed(NamedTuple):
    """A command typed at the console, and what it left.

    Attributes:
        word: what the command was typed to write first.
        marker: the fields the command wrote: the word, the terminal it ran on, and the board's uptime
            when it ran; empty if it did not run.
        record: `keyboard.sh`'s record of how far it got.
    """

    word: str
    marker: list[str]
    record: str


class Console(Part):
    """The board's virtual terminals: X on vt1, and a login prompt on tty2."""

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
        brought forward and tty2 given a fresh login; when the test ends, vt1 is put back in front. The
        check is invalid if the keyboard was not created, the board restarted during the outage (taking
        the evidence in /tmp with it), or the command ran with the network up.

        Returns:
            The command, and what it left.
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
        self._board.cleanup.callback(self._restore)
        self._keyboard.type_after(_KEYBOARD_START_SECONDS, _BOUNDS_SECONDS)
        outage.schedule(_OUTAGE_SECONDS)
        time.sleep(Outage.CUT_DELAY_SECONDS + _OUTAGE_SECONDS + 2)
        self._board.reconnect()
        with invalid_if("the board restarted during the outage, and the evidence in /tmp with it"):
            assert self._board.boot_id() == boot_id
        lines, phases, _after_login = self._keyboard.typed_record()
        with invalid_if(f"the virtual keyboard was not created: {self._keyboard.journal()}"):
            assert "device" in phases
        marker = self._keyboard.typed_marker().fields
        if marker:
            cut = outage.read_record()
            with invalid_if(f"the command ran with the network up: {marker}, outage {cut.cut} to {cut.restored}"):
                assert cut.cut is not None and cut.restored is not None and cut.cut < float(marker[2]) < cut.restored
        return Typed(word, marker, "\n".join(lines))

    def _foreground_vt(self) -> str:
        """Read the virtual terminal in the foreground.

        Returns:
            Its number, as `fgconsole` prints it.
        """
        return self._board.run("fgconsole", check=True).text

    def _bring_vt1_forward(self) -> None:
        """Make vt1 the foreground terminal, restarting `kiosk.service`, whose X takes vt1, if it is not."""
        if self._foreground_vt() != "1":
            self._board.run("systemctl restart kiosk.service", check=True)
            self._board.seconds_until(lambda: self._foreground_vt() == "1")

    def _kill_tty2_login(self) -> None:
        """Kill whatever runs on tty2; `getty@.service`'s `Restart=always` brings back a fresh prompt.

        A logged-in shell outlasts a plain restart until systemd's stop timeout, so the unit is killed.
        """
        self._board.run("systemctl kill -s KILL getty@tty2.service")

    def _restore(self) -> None:
        """Put vt1 back in the foreground with a fresh tty2 login."""
        self._keyboard.press_vt1_chord()
        self._kill_tty2_login()
        self._bring_vt1_forward()
        assert self._foreground_vt() == "1", "vt1 is not the foreground console after the test"
