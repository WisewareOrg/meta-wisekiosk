"""What the panel shows: window titles, and the in-page probe read back through them.

The titles also say which load surf has finished.
"""

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
from board import Board
from record import Record
from replay import FULL_CARDS

_PROBE_SRC = Path(__file__).resolve().parent / "probe.js"
_SURF_DIR = "/home/root/.surf"
_SURF_SCRIPT_PATH = f"{_SURF_DIR}/script.js"
_PANEL_WAIT_SECONDS = 90
_FULL_WAIT_SECONDS = 120
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


class Held(NamedTuple):
    """One read of the board while the backend is held.

    Attributes:
        running: the browser is running.
        served: the page is served.
        shown: what the browser shows: `("probe", sample)` for a settled page from another origin or
            in the app's configuration-error or unreachable-backend state; `("title", title)` for a
            finished load's title seen on this read and the one before with no sample; else None.
        title: the finished load's title when there is no sample, else None.
    """

    running: bool
    served: bool
    shown: tuple | None
    title: str | None


class Panel:
    """What the panel shows: the window titles, and the probe `install` puts in the browser.

    `install` puts the probe in the browser and records `probe_sha256`. Every read is one walk of the
    windows. `assert_loaded_without_backend` waits until the browser has finished a load without the
    backend; `time_on_panel_after_backend_answers` then times from the backend's first answer to the
    instance on the panel.

    Attributes:
        last_reading: the last successful `read`, None before one, and reset by each wait on the panel.
        last_held: the last successful read of `assert_loaded_without_backend`, None before one, and
            reset by it.
    """

    last_reading: PanelRead | None = None
    last_held: Held | None = None

    def __init__(self, board: Board, request: pytest.FixtureRequest, record: Record) -> None:
        """Bind to the board, and to the request whose teardown undoes `install`.

        Args:
            board: the board under test.
            request: registers `install`'s undos.
            record: records the probe's hash and what `assert_loaded_without_backend` read.
        """
        self._board = board
        self._request = request
        self._record = record
        self.last_reading = None
        self.last_held = None
        # the held check's last finished title
        self._previous_title: str | None = None

    def install(self, restart_browser: bool = True) -> None:
        """Load the probe into the browser and record its sha256 as `probe_sha256`.

        The probe is bind-mounted over surf's script path, then the browser restarts to load it;
        with `restart_browser` False the next load surf finishes loads it. Each undo is registered
        once its step has succeeded, except the browser restart's, registered before the bind mount
        so teardown unmounts the probe, removes its copy, then restarts the browser.

        Args:
            restart_browser: restart the browser now, so it loads the probe.
        """
        board = self._board
        board.run(f"mkdir -p {_SURF_DIR} && touch {_SURF_SCRIPT_PATH}", check=True)
        self._request.addfinalizer(lambda: board.run("systemctl restart kiosk.service", check=True))
        board.bind(self._request, _PROBE_SRC, _SURF_SCRIPT_PATH)
        if restart_browser:
            board.run("systemctl restart kiosk.service", check=True)
        self._record(probe_sha256=hashlib.sha256(_PROBE_SRC.read_bytes()).hexdigest())

    @staticmethod
    def on_panel(sample: dict[str, str] | None) -> bool:
        """The app applied, served by the board's own backend; the card count is never judged.

        Args:
            sample: the probe's sample, or None.

        Returns:
            Whether the sample shows the instance on the panel.
        """
        return sample is not None and sample["state"] == "applied" and sample["origin"] in _OWN_ORIGINS

    @staticmethod
    def is_full(sample: dict[str, str] | None) -> bool:
        """The page on the panel with every card live.

        Args:
            sample: the probe's sample, or None.

        Returns:
            Whether the sample shows the instance on the panel with every card live.
        """
        return Panel.on_panel(sample) and sample["cards"] == FULL_CARDS

    def read(self) -> PanelRead:
        """Walk the windows once.

        Returns:
            The read.
        """
        uptime, stdout, _stderr, _returncode = self._board.run_with_uptime(_TITLES_WALK)
        titles = [match.group(1) for match in map(_WM_NAME.match, stdout) if match]
        sample = None
        for title in titles:
            if "WK1 " in title:
                tokens = title.split("WK1 ", 1)[1].split()
                found = dict(token.split("=", 1) for token in tokens if "=" in token)
                if all(key in found for key in _PROBE_FIELDS):
                    sample = found
                    break
        self.last_reading = PanelRead(uptime, sample, titles)
        return self.last_reading

    def wait_until(
        self,
        done: Callable[[PanelRead], object],
        within: float,
        every: float = 1,
        since: float | None = None,
    ) -> tuple[float | None, PanelRead | None]:
        """Read the panel every `every` seconds until `done` accepts a read, or `within` seconds pass.

        Resets `last_reading` first, so an earlier wait's read never stands in for this one's.

        Args:
            done: whether a read ends the wait.
            within: seconds from `since` after which the wait gives up.
            every: seconds slept between reads.
            since: the `time.monotonic()` instant the wait counts from; now when None.

        Returns:
            What `Board.wait_until` returns: the seconds to the done read (None if it gave up) and the
            final read.
        """
        self.last_reading = None
        return self._board.wait_until(self.read, done, within, every, since)

    def wait_on_panel(self, full: bool = False) -> tuple[float, dict[str, str]]:
        """Wait until the instance is on the panel, with every card live when `full`.

        Args:
            full: wait for every card live, not just the instance applied.

        Returns:
            The uptime and the sample of the read that found it.
        """
        judge = self.is_full if full else self.on_panel
        wait = _FULL_WAIT_SECONDS if full else _PANEL_WAIT_SECONDS
        seconds, found = self.wait_until(lambda read: judge(read.sample), wait)
        assert seconds is not None, (
            f"the page was not {'in full state' if full else 'on the panel'} within {wait} s; "
            f"last sample: {self.last_reading.sample if self.last_reading else None!r}"
        )
        return found.uptime, found.sample

    def assert_loaded_without_backend(self) -> None:
        """Wait until the browser has finished a load without the backend, the page not served.

        Records the last read as `held_state` and which case of `shown` matched as `held_case`, then
        fails the test as INVALID if the browser never finished the load within `Board.GIVE_UP_SECONDS`
        or the page was served first, so the hold was too short.
        """
        self.last_held = None
        held_s, _ = self._board.wait_until(
            self._held, lambda read: read.served or (read.running and read.shown is not None), Board.GIVE_UP_SECONDS
        )
        held = self.last_held
        self._record(held_state=held, held_case=held.shown[0] if held and held.shown else None)
        assert held_s is not None, (
            f"INVALID CHECK, not an appliance failure: the browser had not finished a load without the "
            f"backend within {Board.GIVE_UP_SECONDS} s; last read: {held!r}"
        )
        assert not held.served, (
            "INVALID CHECK, not an appliance failure: the page was served before the browser had "
            f"finished a load without the backend, so the hold was too short; last read: {held!r}"
        )

    def time_on_panel_after_backend_answers(self) -> tuple[float | None, float | None]:
        """Time from the backend's first answer to the instance on the panel.

        Waits until the page is first served, so the answer is read up to one read late, then until
        the instance is on the panel. Resets `last_reading`, which holds the last panel read after.

        Returns:
            The board uptime of the page's first serve, None if it was not served within
            `Board.GIVE_UP_SECONDS`; and the seconds from it to the instance on the panel, None if
            there was no answer or it did not come within `Board.GIVE_UP_SECONDS`.
        """
        self.last_reading = None
        answered_s, answered = self._board.wait_until(
            self._board.fetch_page, lambda read: read[1], Board.GIVE_UP_SECONDS
        )
        answered_uptime_s = answered[0] if answered_s is not None else None
        on_panel_s = None
        if answered_uptime_s is not None:
            self.wait_until(lambda read: self.on_panel(read.sample), Board.GIVE_UP_SECONDS)
            last = self.last_reading
            if last and self.on_panel(last.sample):
                on_panel_s = round(last.uptime - answered_uptime_s, 1)
        return answered_uptime_s, on_panel_s

    def _held(self) -> Held:
        """Read the board once for `assert_loaded_without_backend`, against the previous read's title.

        A finished title counts only once a second read shows it unchanged with still no sample: a
        page carrying the probe can show its title before the probe first writes.

        Returns:
            The read.
        """
        running = self._board.run("pgrep -x surf")[2] == 0
        served = self._board.fetch_page()[1]
        _uptime, sample, titles = self.read()
        title = None
        if sample is not None:
            settled = sample["origin"] not in _OWN_ORIGINS or sample["state"] in _SETTLED_APP_STATES
            shown = ("probe", sample) if settled else None
        else:
            # a title with no page title after the ` | ` is a window that has loaded nothing yet
            title = next(
                (t for t in titles if not t.startswith("[") and " | " in t and t.split(" | ", 1)[1]),
                None,
            )
            shown = ("title", title) if title and title == self._previous_title else None
        self._previous_title = title
        self.last_held = Held(running, served, shown, title)
        return self.last_held
