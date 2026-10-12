"""Deploys the DOM probe to the board and reads its latest window-title payload."""

import time
from pathlib import Path

from verdicts.applied import read_sample, verdict

_SCRIPT_PATH = "/home/root/.surf/script.js"
_PROBE_SRC = Path(__file__).resolve().parent / "probe.js"
# Walks the root's whole tree and reads every window's WM_NAME.
_TITLES_PROBE = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | "
    "awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)

APPLIED_WAIT_SECONDS = 90
_POLL_SECONDS = 2


class Probe:
    """Deploys `probe.js` to the board, restarts the browser, and reads its latest sample.

    Holds the labgrid SSHDriver; every method is one transport call -- the judgement lives in
    `verdicts.applied`, never here.
    """

    def __init__(self, driver):
        """Bind one Probe to a board.

        Args:
            driver: A labgrid SSHDriver bound to the `main` target.
        """
        self._driver = driver

    def deploy(self):
        """Copy `probe.js` to the path surf's own userscript config points at.

        Raises:
            RuntimeError: the board could not create the destination directory.
        """
        _stdout, stderr, rc = self._driver.run("mkdir -p /home/root/.surf")
        if rc != 0:
            raise RuntimeError(f"could not create /home/root/.surf: {stderr}")
        self._driver.put(str(_PROBE_SRC), _SCRIPT_PATH)

    def remove(self):
        """Delete the deployed `probe.js`, so a later run sees surf with no userscript."""
        self._driver.run(f"rm -f {_SCRIPT_PATH}")

    def restart_browser(self):
        """Restart `kiosk.service`, so surf reloads the page and (re-)evaluates `probe.js`.

        Raises:
            RuntimeError: `systemctl restart kiosk.service` exited non-zero.
        """
        _stdout, stderr, rc = self._driver.run("systemctl restart kiosk.service")
        if rc != 0:
            raise RuntimeError(f"could not restart kiosk.service: {stderr}")

    def titles(self):
        """The device's window titles, through xprop's WM_NAME walk -- transport only, raw text.

        Returns:
            str: xprop's raw per-window dump, one `WM_NAME(<type>) = "<title>"` line per window
                `xwininfo -tree` found.
        """
        stdout, _stderr, _rc = self._driver.run(_TITLES_PROBE)
        return "\n".join(stdout)


def wait_applied(titles_reader, deadline_s=APPLIED_WAIT_SECONDS):
    """Poll `titles_reader` until a sample reads state=applied, or raise at the deadline.

    Args:
        titles_reader: A `probe` fixture's own reader callable (raw `titles()` text in, per
            call).
        deadline_s (float): Seconds to keep polling.

    Returns:
        dict: `read_sample`'s typed result for the first sample whose state is "applied".

    Raises:
        RuntimeError: `deadline_s` elapsed with no applied sample.
    """
    deadline = time.monotonic() + deadline_s
    samples = []
    while True:
        samples.append(read_sample(titles_reader()))
        outcome, reason = verdict(samples)
        if outcome == "applied":
            return samples[-1]
        if time.monotonic() >= deadline:
            raise RuntimeError(f"the page did not apply within {deadline_s}s ({outcome}:{reason})")
        time.sleep(_POLL_SECONDS)
