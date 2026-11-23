"""The app's page in the browser, read through the window titles and the in-page probe."""

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from board.part import Part

_PROBE_SRC = Path(__file__).resolve().parents[2] / "target_suite" / "probe.js"
_SURF_DIR = "/home/root/.surf"
_SURF_SCRIPT_PATH = f"{_SURF_DIR}/script.js"
_PANEL_WAIT_SECONDS = 90
_ALL_CARDS_LIVE_WAIT_SECONDS = 120
# the page under replay: four park cards, all live
_ALL_CARDS_LIVE = "4/4"
_OWN_ORIGINS = ("http://localhost:8080", "http://127.0.0.1:8080")
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


class Page(Part):
    """The app's page in the browser, as the window titles and the probe report it.

    Attributes:
        last_read: the last read that succeeded, None before one; each wait on the panel resets it.
    """

    last_read: PanelRead | None = None

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
        walk = self._board.run(_TITLES_WALK, with_uptime=True)
        titles = [match.group(1) for match in map(_WM_NAME.match, walk.stdout) if match]
        self.last_read = PanelRead(walk.uptime_s, self._probe_sample(titles), titles)
        return self.last_read

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
