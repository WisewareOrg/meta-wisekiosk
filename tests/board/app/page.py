"""The app's page in the browser, read through the window titles and the in-page probe."""

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from board.app.panel_watch import PanelWatch

if TYPE_CHECKING:
    from record import Record

    from board import Board

_PROBE_SRC = Path(__file__).resolve().parents[2] / "target_suite" / "probe.js"
_SURF_DIR = "/home/root/.surf"
_SURF_SCRIPT_PATH = f"{_SURF_DIR}/script.js"
_PANEL_WAIT_SECONDS = 90
_ALL_CARDS_LIVE_WAIT_SECONDS = 120
# the page under replay: four park cards, all live
_ALL_CARDS_LIVE = "4/4"
_COUNTERS = ("el", "frames", "isum", "ticks", "moving", "changes", "cost")
_HISTOGRAM_BINS = 7
# how often TST032's watch reads the page and the panel after the kill
_KILL_WATCH_POLL_SECONDS = 0.5
_OWN_ORIGINS = ("http://localhost:8080", "http://127.0.0.1:8080")
_SETTLED_APP_STATES = ("error:configuration", "error:backend-unreachable")
_PROBE_FIELDS = ("nonce", "state", "cards", "origin", "layout")
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')
_TITLES_WALK = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)


class PanelRead(NamedTuple):
    """One walk of the windows.

    Attributes:
        uptime: the board's uptime at the walk, in seconds.
        sample: the probe's sample, None if no window carried a payload.
        titles: every window's title.
    """

    uptime: float
    sample: dict[str, str] | None
    titles: list[str]

    @property
    def instance_loaded_title(self) -> str | None:
        """The title of a window surf has finished loading the instance's page into.

        surf titles a window `<indicators>:<indicators> | <page title>`, prefixed `[NN%] ` while the
        page loads; the instance's page title is `WiseKiosk`.

        Returns:
            The title, or None if there is none.
        """
        return next((t for t in self.titles if t.endswith(" | WiseKiosk") and not t.startswith("[")), None)

    def counters(self) -> tuple[dict[str, int], list[int]]:
        """The probe's counters, and its histogram of frame intervals.

        Returns:
            Each counter as an int, by name, and the histogram's counts, one per bin.

        Raises:
            AssertionError: a counter is missing or malformed.
        """
        try:
            values = {key: int(self.sample[key]) for key in _COUNTERS}
            histogram = [int(count) for count in self.sample["hist"].split(",")]
            assert len(histogram) == _HISTOGRAM_BINS
        except (KeyError, ValueError, AssertionError):
            raise AssertionError(f"the probe's counters are missing from {self.sample!r}") from None
        return values, histogram


class HeldRead(NamedTuple):
    """One read of the board while the backend is held.

    Attributes:
        running: the browser is running.
        served: the page is served.
        shown: a settled page the browser loaded without the backend: `("probe", sample)` for a probe
            sample from another origin, or in the app's configuration-error or unreachable-backend
            state; `("title", title)` for a finished load's title seen with no sample on this read and
            the one before; else None. On the app's own origin, a loading or not-yet-mounted app is
            not settled.
        title: the finished load's title when there is no sample, else None.
    """

    running: bool
    served: bool
    shown: tuple | None
    title: str | None


class BackendKillRecovery(NamedTuple):
    """What the page and the panel showed after the backend was killed.

    Attributes:
        answered_uptime_s: the board uptime at which the page was first served after the kill, None if
            it was not.
        on_panel_s: the seconds from the kill to the first read showing the instance on the panel with
            the backend answering, by board uptime, None if there was none.
        left_panel: whether any read after the kill did not show the instance on the panel.
    """

    answered_uptime_s: float | None
    on_panel_s: float | None
    left_panel: bool


class Page:
    """The app's page in the browser, as the window titles and the probe report it.

    Attributes:
        last_read: the last read that succeeded, None before one; each wait on the panel resets it.
    """

    last_read: PanelRead | None

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board
        self.last_read = None

    def install_probe(self, restart_browser: bool = True) -> str:
        """Load the probe into the browser, until the test ends.

        The probe is bind-mounted over surf's script path, then the browser restarts to load it; with
        `restart_browser` False the next load surf finishes loads it. The browser restart's undo is
        registered before the bind mount, so when the test ends the probe is unmounted and its copy
        removed before the browser restarts.

        Args:
            restart_browser: restart the browser now, so it loads the probe.

        Returns:
            The probe's sha256.
        """
        self._board.run(f"mkdir -p {_SURF_DIR} && touch {_SURF_SCRIPT_PATH}", check=True)
        self._board.cleanup.callback(self._board.run, "systemctl restart kiosk.service", check=True)
        self._board.bind_over(_PROBE_SRC, _SURF_SCRIPT_PATH)
        if restart_browser:
            self._board.run("systemctl restart kiosk.service", check=True)
        return hashlib.sha256(_PROBE_SRC.read_bytes()).hexdigest()

    @staticmethod
    def shows_instance(sample: dict[str, str] | None) -> bool:
        """Whether a sample shows the app applied, served by the board's own backend.

        The card count is never judged.

        Args:
            sample: the probe's sample, or None.

        Returns:
            True if the sample shows the instance on the panel.
        """
        return sample is not None and sample["state"] == "applied" and sample["origin"] in _OWN_ORIGINS

    def kill_browser(self) -> float:
        """SIGKILL the browser.

        Returns:
            The board's uptime at the kill.
        """
        return self._board.run_with_uptime("kill -KILL $(pgrep -x surf)", check=True)[0]

    def freeze_browser(self) -> tuple[float, list[str]]:
        """Stop every web process of the browser with SIGSTOP; they are continued when the test ends.

        Returns:
            The board's uptime at the stop, and the pids stopped.
        """
        frozen_at, stdout, _stderr, _returncode = self._board.run_with_uptime(
            's=$(pgrep -x surf); p=$(pgrep -P "$s" WebKitWebProcess); echo $p; kill -STOP $p'
        )
        pids = stdout[0].split()
        if pids:
            self._board.cleanup.callback(self._board.run, f"kill -CONT {' '.join(pids)}")
        return frozen_at, pids

    def web_process_states(self, pids: list[str]) -> dict[str, str | None]:
        """Read each web process's state, as `/proc/<pid>/status` names it.

        Args:
            pids: the web processes.

        Returns:
            Each pid's state letter (`T` for stopped), None where it could not be read.
        """
        states = {}
        for pid in pids:
            status = self._board.run(f"grep '^State:' /proc/{pid}/status")[0]
            states[pid] = status[0].split()[1] if status else None
        return states

    def load_log(self) -> list[str]:
        """Read the browser's page-load lines from this boot's journal.

        Returns:
            The lines, with their monotonic stamps.
        """
        return self._board.run(
            "journalctl -b -u kiosk.service -o short-monotonic --no-pager | grep -F 'surf: page'", timeout=None
        )[0]

    @staticmethod
    def shows_all_cards_live(sample: dict[str, str] | None) -> bool:
        """Whether a sample shows the instance on the panel with every card of the replayed page live.

        Args:
            sample: the probe's sample, or None.

        Returns:
            True if the sample shows the instance with all four cards live.
        """
        return Page.shows_instance(sample) and sample["cards"] == _ALL_CARDS_LIVE

    def wait_for_instance(self, all_cards_live: bool = False) -> tuple[float, dict[str, str]]:
        """Wait until the instance is on the panel, with every card live when `all_cards_live`.

        Args:
            all_cards_live: wait for every card of the replayed page live, not only the instance.

        Returns:
            The board uptime and the sample of the read that found it.
        """
        shows = self.shows_all_cards_live if all_cards_live else self.shows_instance
        within = _ALL_CARDS_LIVE_WAIT_SECONDS if all_cards_live else _PANEL_WAIT_SECONDS
        found_s, found = self.poll(until=lambda read: shows(read.sample), within=within)
        assert found_s is not None, (
            f"the page was not {'in full state' if all_cards_live else 'on the panel'} within {within} s; "
            f"last sample: {self.last_read.sample if self.last_read else None!r}"
        )
        return found.uptime, found.sample

    def read(self) -> PanelRead:
        """Walk the windows once, into `last_read`.

        Returns:
            The read.
        """
        uptime, stdout, _stderr, _returncode = self._board.run_with_uptime(_TITLES_WALK)
        titles = [match.group(1) for match in map(_WM_NAME.match, stdout) if match]
        self.last_read = PanelRead(uptime, self._probe_sample(titles), titles)
        return self.last_read

    def read_titles(self) -> list[str] | None:
        """Walk the windows once for their titles.

        Returns:
            Every window's title, or None if the walk failed.
        """
        try:
            stdout = self._board.run(_TITLES_WALK)[0]
        except self._board.ERRORS:
            return None
        return [match.group(1) for match in map(_WM_NAME.match, stdout) if match]

    def watch(self, from_uptime: float) -> PanelWatch:
        """Start a tally of the panel's reads over a span.

        Args:
            from_uptime: the board uptime at which the span starts.

        Returns:
            The tally; the test reads the panel through it.
        """
        return PanelWatch(self, from_uptime)

    def poll(
        self,
        *,
        until: Callable[[PanelRead], object],
        within: float,
        every: float = 1,
        since: float | None = None,
        read: Callable[[], PanelRead] | None = None,
    ) -> tuple[float | None, PanelRead | None]:
        """Read the panel every `every` seconds until `until` accepts a read, or `within` seconds pass.

        Resets `last_read` first, so an earlier wait's read never stands in for this one's.

        Args:
            until: whether a read ends the wait.
            within: seconds from `since` after which the wait gives up.
            every: seconds slept between reads.
            since: the `time.monotonic()` instant the wait counts from; now when None.
            read: the read to repeat, returning a `PanelRead` (default: `read`).

        Returns:
            What `Board.poll` returns: the seconds to the accepted read (None if it gave up) and the
            final read.
        """
        self.last_read = None
        return self._board.poll(read or self.read, until=until, within=within, every=every, since=since)

    def assert_loaded_without_backend(self, record: "Record") -> None:
        """Wait until the browser has finished a load without the backend, the page not served.

        Records the last read as `held_state` and which case of `shown` matched as `held_case`, then
        fails the test as INVALID if the browser never finished the load within
        `Board.GIVE_UP_SECONDS` or the page was served first, so the hold was too short.

        Args:
            record: the test's record.
        """
        held: HeldRead | None = None

        def read_held() -> HeldRead:
            """Read the board once, against the previous read's title.

            Returns:
                The read.
            """
            nonlocal held
            held = self._read_while_held(held.title if held else None)
            return held

        held_s, _ = self._board.poll(
            read_held,
            until=lambda read: read.served or (read.running and read.shown is not None),
            within=self._board.GIVE_UP_SECONDS,
        )
        record(held_state=held, held_case=held.shown[0] if held and held.shown else None)
        assert held_s is not None, (
            "INVALID CHECK, not an appliance failure: the browser had not finished a load without the "
            f"backend within {self._board.GIVE_UP_SECONDS} s; last read: {held!r}"
        )
        assert not held.served, (
            "INVALID CHECK, not an appliance failure: the page was served before the browser had "
            f"finished a load without the backend, so the hold was too short; last read: {held!r}"
        )

    def time_on_panel_after_backend_answers(self) -> tuple[float | None, float | None]:
        """Time from the backend's first answer to the instance on the panel.

        Waits until the page is first served, read once a second so up to one read late, then until
        the instance is on the panel. Resets `last_read`, which holds the last good panel read after.

        Returns:
            The board uptime of the page's first serve, None if it was not served within
            `Board.GIVE_UP_SECONDS`; and the seconds from it to the instance on the panel, None if
            there was no answer or the instance was not on the panel within `Board.GIVE_UP_SECONDS`.
        """
        self.last_read = None
        answered_s, answered = self._board.poll(
            self._uptime_and_served, until=lambda read: read[1], within=self._board.GIVE_UP_SECONDS
        )
        if answered_s is None:
            return None, None
        answered_uptime_s = answered[0]
        self.poll(until=lambda read: self.shows_instance(read.sample), within=self._board.GIVE_UP_SECONDS)
        last = self.last_read
        on_panel_s = round(last.uptime - answered_uptime_s, 1) if last and self.shows_instance(last.sample) else None
        return answered_uptime_s, on_panel_s

    def time_on_panel_after_backend_kill(self, killed_at_uptime_s: float) -> BackendKillRecovery:
        """Time from a backend kill to the instance on the panel with the backend answering.

        Reads every 0.5 s: the page, until it is first served, and the panel each time. Only a panel
        read once the backend has answered counts, so the page as it stood at the kill cannot pass. A
        failed page read or panel read is skipped; `last_read` holds the last good panel read after.

        Args:
            killed_at_uptime_s: the board uptime at the kill.

        Returns:
            What the reads showed, within `Board.GIVE_UP_SECONDS` of now.
        """
        answered_uptime_s = None
        left_panel = False

        def read_page_and_panel() -> PanelRead:
            """Read the page if it has not yet answered, then the panel.

            Returns:
                The panel read.
            """
            nonlocal answered_uptime_s, left_panel
            if answered_uptime_s is None:
                try:
                    uptime, served = self._uptime_and_served()
                except self._board.ERRORS:
                    served = False
                if served:
                    answered_uptime_s = uptime
            panel = self.read()
            left_panel = left_panel or not self.shows_instance(panel.sample)
            return panel

        found_s, found = self.poll(
            until=lambda read: answered_uptime_s is not None and self.shows_instance(read.sample),
            within=self._board.GIVE_UP_SECONDS,
            every=_KILL_WATCH_POLL_SECONDS,
            read=read_page_and_panel,
        )
        # the board uptime of the first passing read, so it overstates by up to one read
        on_panel_s = round(found.uptime - killed_at_uptime_s, 1) if found_s is not None else None
        return BackendKillRecovery(answered_uptime_s, on_panel_s, left_panel)

    def _uptime_and_served(self) -> tuple[float, bool]:
        """Fetch the page once, stamped with the board's uptime.

        Returns:
            The board's uptime at the fetch, and whether the page served.
        """
        uptime, stdout, stderr, returncode = self._board.run_with_uptime(
            self._board.PAGE_FETCH_CMD, timeout=self._board.PAGE_ATTEMPT_TIMEOUT_SECONDS
        )
        return uptime, self._board.is_page(returncode, "\n".join(stdout + stderr))

    def _read_while_held(self, previous_title: str | None) -> HeldRead:
        """Read the board once while the backend is held.

        A finished title counts only once a second read shows it unchanged with still no sample: a
        page carrying the probe can show its title before the probe first writes.

        Args:
            previous_title: the previous read's `title`.

        Returns:
            The read.
        """
        running = self._board.run("pgrep -x surf")[2] == 0
        served = self._board.page_served()
        _uptime, sample, titles = self.read()
        title = None
        if sample is not None:
            settled = sample["origin"] not in _OWN_ORIGINS or sample["state"] in _SETTLED_APP_STATES
            shown = ("probe", sample) if settled else None
        else:
            # a title with no page title after the ` | ` is a window that has loaded nothing yet
            title = next((t for t in titles if not t.startswith("[") and " | " in t and t.split(" | ", 1)[1]), None)
            shown = ("title", title) if title and title == previous_title else None
        return HeldRead(running, served, shown, title)

    @staticmethod
    def _probe_sample(titles: list[str]) -> dict[str, str] | None:
        """The first title carrying the probe's required fields, as a dict of every token.

        Args:
            titles: every window's title.

        Returns:
            The sample, or None if no title carries one.
        """
        for title in titles:
            if "WK1 " in title:
                tokens = title.split("WK1 ", 1)[1].split()
                found = dict(token.split("=", 1) for token in tokens if "=" in token)
                if all(key in found for key in _PROBE_FIELDS):
                    return found
        return None
