"""A mouse attached to the board."""

from board.part import invalid_if
from board.virtual_input import VirtualInput

_DIR = "/tmp/test-mouse"
_UNIT = "test-mouse"
_EVEMU = f"LD_LIBRARY_PATH={_DIR} {_DIR}/evemu"
_ATTACH_SECONDS = 1

# an evemu device description, as the keyboard's: three buttons from 0x110, and relative axes `02` x and y
_DESC = """\
N: TST013 mouse
I: 0003 0001 0002 0001
B: 00 07 00 00 00 00 00 00 00
B: 01 00 00 00 00 00 00 00 00
B: 01 00 00 00 00 00 00 00 00
B: 01 00 00 00 00 00 00 00 00
B: 01 00 00 00 00 00 00 00 00
B: 01 00 00 07 00 00 00 00 00
B: 02 03 00 00 00 00 00 00 00
"""
# one move: 20 steps of 5 right and 4 down, 50 ms apart
_EVENTS = "".join(
    f"E: 0.{step * 50_000:06d} {event}\n"
    for step in range(20)
    for event in ("0002 0000 5", "0002 0001 4", "0000 0000 0")
)


class Mouse(VirtualInput):
    """A virtual mouse attached to the board through uinput."""

    def move_over_the_page(self) -> str:
        """Attach the mouse until the test ends, and move it until the page has seen two moves in a row.

        The browser gives the pointer its shape on one move and draws it on the next. The check is invalid if
        the page did not see them.

        Returns:
            Where the page last saw the mouse, as `<x>,<y>`.
        """
        self._put(_DIR, {"mouse.desc": _DESC, "mouse.events": _EVENTS})
        device = f"{_EVEMU}-device {_DIR}/mouse.desc >{_DIR}/device.out"
        self._board.run_later(_UNIT, _ATTACH_SECONDS, f"/bin/sh -c '{device}'")
        with invalid_if("the page did not see the mouse move"):
            self._board.seconds_until(self._move, reads=2)
        return self._board.wait_for(self._board.app.mouse_at)

    def _move(self) -> bool:
        """Move the mouse once.

        Returns:
            Whether the page saw it move.
        """
        before = self._board.app.mouse_at()
        self._board.run(f"{_EVEMU}-play $(grep -o '/dev/input/event[0-9]*' {_DIR}/device.out) <{_DIR}/mouse.events")
        return self._board.app.mouse_at() not in ("", before)
