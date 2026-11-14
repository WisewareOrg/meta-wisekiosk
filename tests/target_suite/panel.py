"""The on-the-panel observation: an in-page probe read back through the browser's window titles."""

import hashlib
import re
import subprocess
import time
from pathlib import Path

from labgrid.driver.exception import ExecutionError

_PROBE_SRC = Path(__file__).resolve().parent / "probe.js"
_PROBE_COPY_PATH = "/tmp/kiosk-probe.js"
_SURF_DIR = "/home/root/.surf"
_SURF_SCRIPT_PATH = f"{_SURF_DIR}/script.js"
_PANEL_WAIT_SECONDS = 90
_PANEL_POLL_SECONDS = 1
FULL_CARDS = "4/4"
OWN_ORIGINS = ("http://localhost:8080", "http://127.0.0.1:8080")
_PROBE_FIELDS = ("nonce", "state", "cards", "origin")
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')
_TITLES_WALK = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)


def _probe_sample(xprop_output):
    """The first window title carrying the probe's four fields, as a dict of every token, else None."""
    for line in xprop_output.splitlines():
        match = _WM_NAME.match(line)
        if match and "WK1 " in match.group(1):
            tokens = match.group(1).split("WK1 ", 1)[1].split()
            found = dict(token.split("=", 1) for token in tokens if "=" in token)
            if all(key in found for key in _PROBE_FIELDS):
                return found
    return None


class Panel:
    """What the panel shows, read through the probe `install` puts in the browser."""

    def __init__(self, board):
        self._board = board

    def install(self, request):
        """Load the probe into the browser and return its sha256.

        The probe is copied to `/tmp` and bind-mounted over surf's script path, then the browser
        restarts to load it. Each undo is registered once its step has succeeded, except the
        browser restart's, registered before the bind mount so teardown unmounts the probe,
        then restarts the browser, then removes the copy.
        """
        board = self._board
        board.put(str(_PROBE_SRC), _PROBE_COPY_PATH)
        request.addfinalizer(lambda: board.run(f"rm -f {_PROBE_COPY_PATH}", check=True))

        board.run(f"mkdir -p {_SURF_DIR} && touch {_SURF_SCRIPT_PATH}", check=True)
        board.run(
            f"if grep -q ' {_SURF_SCRIPT_PATH} ' /proc/self/mountinfo; "
            f"then umount {_SURF_SCRIPT_PATH}; fi",
            check=True,
        )

        request.addfinalizer(lambda: board.run("systemctl restart kiosk.service", check=True))
        board.run(f"mount --bind {_PROBE_COPY_PATH} {_SURF_SCRIPT_PATH}", check=True)
        request.addfinalizer(lambda: board.run(f"umount {_SURF_SCRIPT_PATH}", check=True))

        board.run("systemctl restart kiosk.service", check=True)

        return hashlib.sha256(_PROBE_SRC.read_bytes()).hexdigest()

    @staticmethod
    def on_panel(sample):
        """The app applied, served by the board's own backend; the card count is never judged."""
        return sample is not None and sample["state"] == "applied" and sample["origin"] in OWN_ORIGINS

    def read(self):
        """The board's uptime and the probe's sample (None = no payload), from one command.

        Raises:
            subprocess.TimeoutExpired: the command ran past `Board.run`'s timeout.
        """
        stdout, _stderr, _returncode = self._board.run(f"cat /proc/uptime; {_TITLES_WALK}")
        return float(stdout[0].split()[0]), _probe_sample("\n".join(stdout[1:]))

    def wait_on_panel(self, timeout_s=_PANEL_WAIT_SECONDS):
        """Poll until the instance is on the panel; return that read's (uptime, sample)."""
        deadline = time.monotonic() + timeout_s
        while True:
            uptime_s, sample = self.read()
            if self.on_panel(sample):
                return uptime_s, sample
            assert time.monotonic() < deadline, (
                f"the instance was not on the panel within {timeout_s} s; last sample: {sample!r}"
            )
            time.sleep(_PANEL_POLL_SECONDS)

    def wait_full_state(self, timeout_s):
        """Poll until the page is on the panel with every card live; return that read's (uptime, sample)."""
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                uptime_s, sample = self.read()
            except (ExecutionError, subprocess.TimeoutExpired):
                sample = None
            if self.on_panel(sample) and sample["cards"] == FULL_CARDS:
                return uptime_s, sample
            assert time.monotonic() < deadline, (
                f"the page was not in full state within {timeout_s} s; last sample: {sample!r}"
            )
            time.sleep(_PANEL_POLL_SECONDS)
