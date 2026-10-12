"""Deploys the DOM probe to the board and reads its latest window-title payload."""

from pathlib import Path

from verdicts.applied import read_fields

_SCRIPT_PATH = "/home/root/.surf/script.js"
_PROBE_SRC = Path(__file__).resolve().parent / "probe.js"
# Walks the root's whole tree and reads every window's WM_NAME.
_TITLES_PROBE = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | "
    "awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)


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

    def read(self):
        """The first window's own probe payload, untyped, or None if no window carries one.

        Every token past the probe's own marker, unfiltered and unconverted -- the shape every
        test here needs, including the performance window's own extra fields that the
        narrower, typed `read_sample` does not carry.

        Returns:
            dict | None: `verdicts.applied.read_fields`'s own result over `self.titles()`.
        """
        return read_fields(self.titles())
