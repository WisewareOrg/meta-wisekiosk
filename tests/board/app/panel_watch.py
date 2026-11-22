"""The panel read once a second over a span, tallied."""

import subprocess
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from labgrid.driver.exception import ExecutionError

if TYPE_CHECKING:
    from board.app.page import Page

_READ_PAUSE_SECONDS = 1


class PanelWatch:
    """The panel's reads over a span, tallied.

    Attributes:
        reads: how many reads were attempted.
        failed: how many reads failed or carried no sample.
        off_panel: how many reads did not show the instance on the panel.
        uptimes: the board uptime of the span's start, of each successful read, and of any instant
            the test adds.
        on_panel_at: the board uptime of the span's start, and of each read that showed the instance
            on the panel.
        nonces: every nonce seen with the instance on the panel.
    """

    reads: int
    failed: int
    off_panel: int
    uptimes: list[float]
    on_panel_at: list[float]
    nonces: set[str]

    def __init__(self, page: "Page", from_uptime: float) -> None:
        """Start the tally at the span's start.

        Args:
            page: the page whose reads are tallied.
            from_uptime: the board uptime at which the span starts.
        """
        self._page = page
        self.reads = 0
        self.failed = 0
        self.off_panel = 0
        self.uptimes = [from_uptime]
        self.on_panel_at = [from_uptime]
        self.nonces = set()

    def read_while(self, keep_going: Callable[[], bool]) -> None:
        """Read the panel once a second while `keep_going()`, tallying each read.

        Args:
            keep_going: whether to read again.
        """
        while keep_going():
            self.reads += 1
            try:
                read = self._page.read()
            except (ExecutionError, subprocess.TimeoutExpired):
                self.failed += 1
                self.off_panel += 1
            else:
                self.uptimes.append(read.uptime)
                if read.sample is None:
                    self.failed += 1
                if self._page.shows_instance(read.sample):
                    self.on_panel_at.append(read.uptime)
                    self.nonces.add(read.sample["nonce"])
                else:
                    self.off_panel += 1
            time.sleep(_READ_PAUSE_SECONDS)

    def longest_stop_s(self, until_uptime: float, observation_end: float) -> float:
        """The longest interval between on-panel reads that starts by `until_uptime`.

        An interval runs from an on-panel read to the next; the last runs to the end of observation.

        Args:
            until_uptime: the board uptime after which an on-panel read no longer starts an interval.
            observation_end: the board uptime at which the panel stopped being watched.

        Returns:
            The seconds, to 0.1 s.
        """
        starts = [at for at in self.on_panel_at if at <= until_uptime]
        ends = self.on_panel_at[1:] + [observation_end]
        return round(max(end - start for start, end in zip(starts, ends, strict=False)), 1)
