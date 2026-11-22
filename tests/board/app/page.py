"""The app's page in the browser, read through the window titles and the in-page probe."""

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from record import Record

    from board import Board

_PROBE_SRC = Path(__file__).resolve().parents[2] / "target_suite" / "probe.js"
_SURF_DIR = "/home/root/.surf"
_SURF_SCRIPT_PATH = f"{_SURF_DIR}/script.js"
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
