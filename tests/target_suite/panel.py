"""The on-the-panel observation: read what the browser's window titles say the probe saw."""

import time

from verdicts.applied import on_panel, read_sample

WAIT_SECONDS = 90
POLL_SECONDS = 1

# Walks the root window's whole tree and prints every window's WM_NAME.
_TITLES_WALK = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)


class Panel:
    """What the panel shows, read through the probe `panel` (conftest.py) puts in the browser."""

    def __init__(self, board):
        """Bind to the board.

        Args:
            board (Board): the board under test (tests/conftest.py).
        """
        self._board = board

    def read(self):
        """The board's uptime and the probe's current sample, from one board command.

        Returns:
            tuple[float, dict[str, str] | None]: the board's uptime in seconds, the frame every
                bound here is measured in, and the sample `verdicts.applied.read_sample` finds
                in the window titles (None = no probe payload).

        Raises:
            subprocess.TimeoutExpired: the command ran past `Board.run`'s timeout.
        """
        stdout, _stderr, _returncode = self._board.run(f"cat /proc/uptime; {_TITLES_WALK}")
        return float(stdout[0].split()[0]), read_sample("\n".join(stdout[1:]))

    def wait_on_panel(self, timeout_s=WAIT_SECONDS):
        """Poll until the WiseKiosk instance is on the panel.

        Args:
            timeout_s (float): how long to poll, on the host's monotonic clock.

        Returns:
            tuple[float, dict[str, str]]: the `read` of the first read where `on_panel` holds.

        Raises:
            AssertionError: `timeout_s` passed first; the message names the last sample.
            subprocess.TimeoutExpired: a read ran past `Board.run`'s timeout.
        """
        deadline = time.monotonic() + timeout_s
        while True:
            uptime_s, sample = self.read()
            if on_panel(sample):
                return uptime_s, sample
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"the instance was not on the panel within {timeout_s} s; "
                    f"last sample: {sample!r} (None = no probe payload)"
                )
            time.sleep(POLL_SECONDS)
