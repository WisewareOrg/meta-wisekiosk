"""Target suite: the display server's screen saver and power management are off."""

import re
from collections.abc import Callable

from board import Board

_TIMEOUT = re.compile(r"timeout:\s+(\d+)")
_DPMS_HEADER = "DPMS (Display Power Management Signaling):"
# power management is off when it is disabled, or the server has no such extension
_DPMS_OFF = ("DPMS is Disabled", "Server does not have the DPMS Extension")


def test_display_blanking_disabled(board: Board, record_property: Callable[[str, object], None]) -> None:
    """TST007 display blanking disabled: `xset q` shows a zero screen-saver timeout and DPMS off.

    Args:
        board: the board under test, whose X server is asked.
        record_property: records the requirement and `xset q`'s output.

    Raises:
        AssertionError: the screen saver timeout is missing or not 0, or power management is not off.
    """
    record_property("requirement", "TST007")
    output = board.read("DISPLAY=:0 xset q")
    record_property("xset_q", output)

    match = _TIMEOUT.search(output)
    assert match is not None, f"no screen saver timeout in xset's output: {output!r}"
    assert match.group(1) == "0", f"the screen saver timeout is {match.group(1)} s, not 0"
    dpms = output.partition(_DPMS_HEADER)[2].strip() or "no DPMS section"
    assert any(text in output for text in _DPMS_OFF), (
        f"display power management is not off; the DPMS part reads: {dpms!r}"
    )
