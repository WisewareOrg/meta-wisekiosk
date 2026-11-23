"""The WiseKiosk app on the board: its backend, the browser showing it, and the in-page probe that reports it."""

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from board.app.backend import Backend
from board.app.config import Config
from board.app.page import Page
from board.part import Part, invalid_if
from board.process import Process
from board.unit import Unit

if TYPE_CHECKING:
    from board import Board

# busybox wget returns 0 only on 2xx
_FETCH = "wget -q -O- http://127.0.0.1:8080/"
_FETCH_TIMEOUT_SECONDS = 10
_PROBE = Path(__file__).resolve().parents[2] / "target_suite" / "probe.js"
_SURF_SCRIPT = "/home/root/.surf/script.js"
_OWN_ORIGINS = ("http://localhost:8080", "http://127.0.0.1:8080")
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')
_TITLES = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)
# how long a crashed backend is held down, so the browser starts without it
_BACKEND_HOLD_SECONDS = 60


class App(Part):
    """The WiseKiosk app on the board, and the browser showing it on the panel.

    Attributes:
        backend: wisekiosk.service, which serves the instance's page.
        browser: the browser, surf.
        config: the config the app runs with.
        page: the app's page in the browser.
    """

    backend: Backend
    browser: Process
    config: Config
    page: Page

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        super().__init__(board)
        self.backend = Backend(board, "wisekiosk.service")
        self.browser = Process(board, "surf")
        self.config = Config(board)
        self.page = Page(board)
        self._kiosk = Unit(board, "kiosk.service")
        self._web_processes = Process(board, "WebKitWebProcess", parent="surf")

    def install_probe(self) -> None:
        """Load the probe into the browser, which restarts to load it, until the test ends.

        The browser restart's undo is registered before the bind mount, so when the test ends the probe
        is unmounted and its copy removed before the browser restarts.
        """
        self._board.run(f"mkdir -p {Path(_SURF_SCRIPT).parent} && touch {_SURF_SCRIPT}", check=True)
        self._board.cleanup.callback(self._kiosk.restart)
        self._board.bind_over(_PROBE, _SURF_SCRIPT)
        self._kiosk.restart()

    def is_served(self) -> bool:
        """Whether the backend serves the instance's page.

        Returns:
            True if a fetch of the page returned an HTML document.
        """
        fetch = self._board.run(_FETCH, timeout=_FETCH_TIMEOUT_SECONDS)
        return fetch.returncode == 0 and "<html" in fetch.output

    def is_up(self) -> bool:
        """Whether the instance's page is served with the browser running.

        Returns:
            True if both hold.
        """
        return self.browser.is_running() and self.is_served()

    def on_panel(self) -> bool:
        """Whether the instance is on the panel: its page served, and the probe reporting it applied.

        The probe must report the app's own page, from the board's own backend.

        Returns:
            True if both hold.
        """
        sample = self._sample()
        applied = sample is not None and sample["state"] == "applied" and sample["origin"] in _OWN_ORIGINS
        return applied and self.is_served()

    def wait_until_on_panel(self) -> None:
        """Wait until the instance is on the panel."""
        self._board.seconds_until(self.on_panel)

    def freeze_page(self) -> float:
        """Freeze the page without ending the browser: stop its web processes, until the test ends.

        The check is invalid if the panel was not changing before the freeze, or did not stand still
        after it.

        Returns:
            The host `time.monotonic()` just before the freeze.
        """
        screen = self._board.screen
        with invalid_if("the panel was not changing before the freeze"):
            self._board.seconds_until(screen.is_changing, reads=3)
        frozen_at = self._web_processes.stop()
        with invalid_if("the panel did not stand still after the freeze"):
            self._board.seconds_until(screen.stands_still)
        return frozen_at

    def kill_backend_while_browser_starts(self) -> float:
        """Kill the backend outright, and start the browser again while the backend is down.

        The backend's own restart is held back until the test ends or 60 s pass, so the browser loads
        a page without it; the check is invalid if it did not.

        Returns:
            The host `time.monotonic()` at which the backend was first seen answering again.
        """
        self.backend.drop_in(f"[Service]\\nRestartSec={_BACKEND_HOLD_SECONDS}\\n")
        self.backend.kill()
        self._kiosk.restart()
        with invalid_if("the browser did not load a page while the backend was down"):
            self._board.seconds_until(self._loaded_a_page)
            assert not self.is_served(), "the backend answered first"
        self._board.seconds_until(self.is_served)
        return time.monotonic()

    def _titles(self) -> list[str]:
        """Read every window's title.

        Returns:
            The titles.
        """
        return [match[1] for match in map(_WM_NAME.match, self._board.run(_TITLES).stdout) if match]

    def _loaded_a_page(self) -> bool:
        """Whether the browser has finished loading a page.

        surf titles a window `<indicators> | <page title>`, prefixed `[NN%] ` while a page loads.

        Returns:
            True if a window carries a finished page's title.
        """
        return any(not title.startswith("[") and title.partition(" | ")[2] for title in self._titles())

    def _sample(self) -> dict[str, str] | None:
        """Read the probe's latest report, from the title it writes.

        Returns:
            Each `key=value` token of the report, or None if no window carries one.
        """
        for title in self._titles():
            if "WK1 " in title:
                report = dict(token.split("=", 1) for token in title.split("WK1 ", 1)[1].split() if "=" in token)
                if {"state", "origin"} <= report.keys():
                    return report
        return None
