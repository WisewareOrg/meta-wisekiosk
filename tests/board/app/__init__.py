"""The WiseKiosk app on the board: its backend, the browser showing it, and the in-page probe that reports it."""

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from board.app.backend import Backend
from board.app.config import Config
from board.part import Part, invalid_if
from board.process import Process
from board.unit import Unit

if TYPE_CHECKING:
    from wisebench.proxy import Proxy

    from board import Board

# busybox wget returns 0 only on 2xx
_FETCH = "wget -q -O- http://127.0.0.1:8080/"
_FETCH_TIMEOUT_SECONDS = 10
_PROBE = Path(__file__).resolve().parents[2] / "target_suite" / "probe.js"
_SURF_SCRIPT = "/home/root/.surf/script.js"
_OWN_ORIGINS = ("http://localhost:8080", "http://127.0.0.1:8080")
# what opens the title the probe writes its report into
PROBE_TITLE = "WK1 "
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')
_TITLES = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)
# the replayed page complete: four park cards, all live
_ALL_CARDS_LIVE = "4/4"
# the edges of the probe's histogram of frame intervals, as the probe itself sets them
_HISTOGRAM_EDGES_MS = tuple(
    int(edge) for edge in re.search(r"var EDGES = \[([\d, ]+)\]", _PROBE.read_text())[1].split(",")
)
# the least share of the probe's report ticks that caught a marquee scrolling, for a window to count
_MOTION_FLOOR = 0.29
# how long a crashed backend's own restart is held back, so the browser starts without it
_BACKEND_HOLD_SECONDS = 600
# a soft reboot restarts userspace only, so a new boot shows as a new start of multi-user.target
_USERSPACE_BOOT = "systemctl show -p ActiveEnterTimestampMonotonic --value multi-user.target"


class App(Part):
    """The WiseKiosk app on the board, and the browser showing it on the panel.

    Attributes:
        backend: wisekiosk.service, which serves the instance's page.
        browser: the browser, surf.
        config: the config the app runs with.
        kiosk: kiosk.service, which runs X and the browser.
    """

    backend: Backend
    browser: Process
    config: Config
    kiosk: Unit

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        super().__init__(board)
        self.backend = Backend(board, "wisekiosk.service")
        self.browser = Process(board, "surf")
        self.config = Config(board)
        self.kiosk = Unit(board, "kiosk.service")
        self._web_processes = Process(board, "WebKitWebProcess", parent="surf")

    def install_probe(self, restart_browser: bool = True) -> None:
        """Load the probe into the browser, until the test ends.

        The browser restart's undo is registered before the bind mount, so when the test ends the probe
        is unmounted and its copy removed before the browser restarts.

        Args:
            restart_browser: restart the browser so it loads the probe now; else its next page load loads it.
        """
        self._board.run(f"mkdir -p {Path(_SURF_SCRIPT).parent} && touch {_SURF_SCRIPT}", check=True)
        self._board.cleanup.callback(self.kiosk.restart)
        self._board.bind_over(_PROBE, _SURF_SCRIPT)
        if restart_browser:
            self.kiosk.restart()

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

        The probe must report the app's own page, from the board's own backend. The page is read first,
        so the probe's report is the newer of the two.

        Returns:
            True if both hold.
        """
        return self.on_panel_report() is not None

    def on_panel_report(self) -> dict[str, str] | None:
        """Read the probe's report, when it shows the instance on the panel.

        Returns:
            The report, as `on_panel` judges it; None if the instance is not on the panel.
        """
        if not self.is_served():
            return None
        report = self.report()
        on_panel = report is not None and report["state"] == "applied" and report["origin"] in _OWN_ORIGINS
        return report if on_panel else None

    def complete_report(self) -> dict[str, str] | None:
        """Read the probe's report, when it shows the replayed page complete: on the panel, every card live.

        Returns:
            The report; None if the page is not complete.
        """
        report = self.on_panel_report()
        return report if report is not None and report.get("cards") == _ALL_CARDS_LIVE else None

    def all_cards_live(self) -> bool:
        """Whether the replayed page is complete: on the panel, every card live.

        Returns:
            True if it is.
        """
        return self.complete_report() is not None

    def frame_stalls(self, cutoff_ms: int, window_s: float, after_s: float) -> int:
        """Count the page's frame intervals of `cutoff_ms` or longer, over a window of its own time.

        Waits for the page complete, all its cards live. The window opens `after_s` of page time later and
        runs `window_s`; the board is not read inside it. The check is invalid if the page reloaded or
        changed state before the window opened or inside it, or shows too little motion: under 29% of the
        probe's report ticks caught a marquee scrolling.

        Args:
            cutoff_ms: the shortest interval counted; one of the probe's histogram edges.
            window_s: how long the window runs, in seconds of page time.
            after_s: how long after the page is complete the window opens, in seconds of page time.

        Returns:
            The intervals counted.
        """
        complete = self._board.wait_for(self.complete_report)
        start = self._page_time_reached(complete, after_s)
        with invalid_if("the page reloaded or changed state before the window opened"):
            assert start["load"] == complete["load"] and start["changes"] == complete["changes"]
        time.sleep(window_s)
        end = self._page_time_reached(start, window_s)
        with invalid_if("the page reloaded or changed state inside the window"):
            assert end["load"] == start["load"] and end["changes"] == start["changes"]
        ticks, moving = (int(end[key]) - int(start[key]) for key in ("ticks", "moving"))
        with invalid_if(f"too little motion: {moving} of {ticks} report ticks caught a marquee scrolling"):
            assert ticks and moving / ticks >= _MOTION_FLOOR
        stalls_from = _HISTOGRAM_EDGES_MS.index(cutoff_ms) + 1
        return sum(int(count) for count in end["hist"].split(",")[stalls_from:]) - sum(
            int(count) for count in start["hist"].split(",")[stalls_from:]
        )

    def run_behind_replay(self) -> "Proxy":
        """Run the backend behind the test's replay proxy, on its recording's config, until the test ends.

        Returns:
            The proxy, which says which of the recording's requests it answered and which it did not.
        """
        proxy = self._board.fixture("proxy")
        self.backend.put_behind(proxy, Path(proxy.har).parent / "config.json")
        return proxy

    def layout_size(self) -> tuple[int, int]:
        """Read the size the page is laid out at, as the probe reports its viewport.

        Returns:
            Its width and height, in CSS pixels.
        """
        sample = self.report()
        assert sample is not None and "layout" in sample, f"the probe reports no layout: {sample!r}"
        width, _, height = sample["layout"].partition("x")
        return int(width), int(height)

    def wait_until_on_panel(self) -> None:
        """Wait until the instance is on the panel."""
        self._board.seconds_until(self.on_panel)

    def freeze_page(self) -> float:
        """Freeze the page without ending the browser: stop its web processes, until the test ends.

        The page must have finished loading: surf watches a page for answers, and reloads one that stops
        answering, only from then on. The check is invalid if the panel was not changing before the
        freeze, the browser had no web process to stop, or the panel did not stand still after the freeze.

        Returns:
            The host `time.monotonic()` just before the freeze.
        """
        screen = self._board.screen
        with invalid_if("the panel was not changing before the freeze"):
            self._board.seconds_until(screen.is_changing, reads=3)
        with invalid_if("the freeze did not take: no web process of the browser to stop"):
            frozen_at = self._web_processes.stop()
        with invalid_if("the panel did not stand still after the freeze"):
            self._board.seconds_until(screen.stands_still)
        return frozen_at

    def kill_backend_while_browser_starts(self) -> float:
        """Kill the backend outright, and start the browser again while the backend is down.

        The backend's own restart is held back, until the test ends, so the browser loads a page without it;
        the check is invalid if it did not. Then the backend is restarted: a start would wait out the hold.

        Returns:
            The host `time.monotonic()` at the start of the read that first saw the backend answering again.
        """
        self.backend.drop_in(f"[Service]\\nRestartSec={_BACKEND_HOLD_SECONDS}\\n")
        self.backend.kill()
        self.kiosk.restart()
        return self._answers_after_a_load_without_it(self.backend.restart)

    def restart_with_backend_held(self) -> float:
        """Restart the board's userspace with the backend held back until the browser has started.

        The backend is masked for this boot across a soft reboot, then let go once the browser has loaded a
        page without it; the check is invalid if the hold did not survive the restart or the browser loaded
        nothing while it held. A board-side timer lets the backend go anyway once the wait would have
        given up, in case the host goes away.

        Returns:
            The host `time.monotonic()` at the start of the read that first saw the backend answering.
        """
        self.backend.mask()
        self._board.restart_with("systemctl soft-reboot", boot_cmd=_USERSPACE_BOOT)
        self.backend.unmask_later(self._board.GIVE_UP_SECONDS)
        with invalid_if("the backend was not held back across the restart"):
            assert not self.backend.is_active()
        self.install_probe(restart_browser=False)
        return self._answers_after_a_load_without_it(self.backend.unmask)

    def loaded_the_instance(self) -> bool:
        """Whether the browser has finished loading the instance's page, whose title is `WiseKiosk`.

        Returns:
            True if a window carries it, loaded.
        """
        return any(not title.startswith("[") and title.endswith(" | WiseKiosk") for title in self._titles())

    def _answers_after_a_load_without_it(self, release: Callable[[], None]) -> float:
        """Wait until the browser has loaded a page with the backend held down, then let it go.

        The check is invalid if the browser loaded nothing, or the backend answered first.

        Args:
            release: lets the backend go.

        Returns:
            The host `time.monotonic()` at the start of the read that first saw the backend answering, so the
            time counted from it can only overstate.
        """
        with invalid_if("the browser did not load a page while the backend was down"):
            self._board.seconds_until(self._loaded_a_page)
            assert not self.is_served(), "the backend answered first"
        release()

        def answered_at() -> float | None:
            """Read once whether the backend answers.

            Returns:
                The host `time.monotonic()` at the start of the read, if it answered; else None.
            """
            began = time.monotonic()
            return began if self.is_served() else None

        return self._board.wait_for(answered_at)

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

    def report(self) -> dict[str, str] | None:
        """Read the probe's latest report, from the title it writes.

        Returns:
            Each `key=value` token of the report, or None if no window carries one.
        """
        for title in self._titles():
            if PROBE_TITLE in title:
                tokens = title.split(PROBE_TITLE, 1)[1].split()
                report = dict(token.split("=", 1) for token in tokens if "=" in token)
                if {"state", "origin"} <= report.keys():
                    return report
        return None

    def _page_time_reached(self, since: dict[str, str], seconds: float) -> dict[str, str]:
        """Read the probe until `seconds` of page time have passed since the report `since`, or the page reloaded.

        Args:
            since: a report of the probe.
            seconds: the page time to wait.

        Returns:
            The first report past it.
        """

        def reached() -> dict[str, str] | None:
            """Read the probe once.

            Returns:
                The report, if the page reloaded or its time is past the mark; else None.
            """
            report = self.report()
            if report is None or not (
                report["load"] != since["load"] or int(report["el"]) >= int(since["el"]) + seconds * 1000
            ):
                return None
            return report

        return self._board.wait_for(reached)
