"""Target suite: a page frozen without ending the browser is changing on the panel again in time."""

import subprocess
import time
from pathlib import Path

from board_test import BoardTest

_CLOCK_CONFIG = Path(__file__).resolve().parent / "clock-seconds.json"
# TST005's bound
_BOUND_SECONDS = 60
# the freeze must show on the panel within this long, by board uptime
_STOPPED_WITHIN_SECONDS = 15
# how long the test keeps capturing
_GIVE_UP_SECONDS = 120
_CHANGING_READS = 3


class TestFrozenPage(BoardTest):
    """A page frozen without ending the browser is changing on the panel again in time."""

    def test_frozen_page_recovered(self) -> None:
        """TST005 frozen page recovered: stop the page's web processes and time until the panel changes again.

        The board shows a clock with seconds in the middle third. The panel must change three reads
        in a row before the freeze. Every `WebKitWebProcess` of the browser is then stopped with
        SIGSTOP, and the freeze is confirmed from each process's state and from the panel standing
        still within `_STOPPED_WITHIN_SECONDS`. Recovery is the first changing read that starts
        three changing reads in a row; its time is that read's second capture, by board uptime.
        """
        page = self.board.app.page
        captures = self.board.screen.captures
        self.record(probe_sha256=page.install_probe())
        self.record(requirement="TST005")
        self.board.app.config.use(_CLOCK_CONFIG)
        _, before = page.wait_for_instance()
        self.record(crop=captures.crop)
        changing_s, _ = self.board.poll(
            captures.take,
            until=lambda _capture: captures.changing_run >= _CHANGING_READS,
            within=_GIVE_UP_SECONDS,
            every=0,
        )
        assert changing_s is not None, "the panel was not changing before the freeze"

        frozen_at, frozen_pids = page.freeze_browser()
        give_up_at = time.monotonic() + _GIVE_UP_SECONDS
        self.record(frozen_pids=frozen_pids, frozen_at_uptime_s=frozen_at)
        assert frozen_pids, "the freeze did not take: no web process of the browser was found"
        for pid, state in page.web_process_states(frozen_pids).items():
            assert state == "T", f"the freeze did not take: web process {pid} is not stopped ({state!r})"
        while True:
            uptime_s, _digest = captures.take()
            in_time = uptime_s is not None and uptime_s <= frozen_at + _STOPPED_WITHIN_SECONDS
            if in_time and captures.stood_still() and captures.taken[-2][0] > frozen_at:
                break
            assert uptime_s is None or in_time, (
                f"the freeze did not take: the panel was not seen stopped within {_STOPPED_WITHIN_SECONDS} s of it"
            )
            assert time.monotonic() < give_up_at, "the freeze did not take: no reading of the panel"
        recovered_s = None
        while time.monotonic() < give_up_at:
            captures.take()
            if captures.changing_run == _CHANGING_READS:
                recovered_s = round(captures.taken[-_CHANGING_READS][0] - frozen_at, 1)
                break

        try:
            after = page.read().sample
        except subprocess.TimeoutExpired:
            after = None
        self.record(
            before=before,
            after=after,
            recovery_log="\n".join(page.load_log()),
            captures=captures.taken,
            recovered_s=recovered_s,
        )
        assert recovered_s is not None, f"the panel was not changing again within {_GIVE_UP_SECONDS} s of the freeze"
        assert recovered_s <= _BOUND_SECONDS, (
            f"changing again after {recovered_s} s; TST005's bound is {_BOUND_SECONDS} s"
        )
