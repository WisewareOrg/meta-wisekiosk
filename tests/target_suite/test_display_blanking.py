"""Target suite: the display server's screen saver and power management are off."""

import re

_TIMEOUT = re.compile(r"timeout:\s+(\d+)")


def test_display_blanking_disabled(board, record_property):
    """TST007 display blanking disabled: `xset q` shows a zero screen-saver timeout and DPMS disabled."""
    record_property("requirement", "TST007")
    stdout, _stderr, _returncode = board.run("DISPLAY=:0 xset q", check=True)
    output = "\n".join(stdout)
    record_property("xset_q", output)

    match = _TIMEOUT.search(output)
    assert match is not None, f"no screen saver timeout in xset's output: {output!r}"
    assert match.group(1) == "0", f"the screen saver timeout is {match.group(1)} s, not 0"
    assert "DPMS is Disabled" in output, f"display power management is not disabled: {output!r}"
