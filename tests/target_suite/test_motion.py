"""Target suite: the replayed page's motion stays within a bound of frame stalls."""

import time
from typing import TYPE_CHECKING

import pytest
from board_test import BoardTest
from replay import CARDS4_LIVE

if TYPE_CHECKING:
    from wisebench.proxy import Proxy

WARMUP_MS = 40_000
WINDOW_MS = 320_000
# the host sleeps this long inside the window, making no board read
WINDOW_SLEEP_SECONDS = 321
# how long past the window's end the page may take to report it
END_WAIT_SECONDS = 30
READ_PAUSE_SECONDS = 1
# a stall is a frame interval at or above this; the histogram's bin 3 starts here
CUTOFF_MS = 250
STALL_FROM_BIN = 3
# TST009's bound: the most stalls a window may hold
STALL_BOUND = 24
# the longest the start read may take to reach the warm-up
WARMUP_READ_WAIT_SECONDS = 120
# the least share of report ticks that caught a marquee scrolling for the window to count
MOTION_FLOOR = 0.29


class TestMotion(BoardTest):
    """The replayed page's motion stays within a bound of frame stalls."""

    @pytest.mark.parametrize("proxy", [str(CARDS4_LIVE / "flows.har")], indirect=True)
    def test_motion_stutter(self, proxy: "Proxy") -> None:
        """TST009 motion stutter measured: at most `STALL_BOUND` frame stalls in the window.

        The window opens `WARMUP_MS` of page time after the page first reads full state, and the
        host reads nothing from the board between the start read's temperature and the end read.
        The window is invalid, never a pass or a failure, if the page reloaded or changed state, a read
        is not full state, too little motion was seen, or the replay killed a request.

        Args:
            proxy: the proxy replaying the cards4-live recording.
        """
        page = self.board.app.page
        self.board.app.backend.put_behind(proxy, CARDS4_LIVE / "config.json")
        self.record(probe_sha256=page.install_probe())
        _, first = page.wait_for_instance(all_cards_live=True)
        self.record(requirement="TST009", cutoff_ms=CUTOFF_MS, bound=STALL_BOUND)
        warmed_s, start = page.poll(
            until=lambda read: read.sample is not None and int(read.sample["el"]) >= int(first["el"]) + WARMUP_MS,
            within=WARMUP_READ_WAIT_SECONDS,
            every=READ_PAUSE_SECONDS,
        )
        assert warmed_s is not None, (
            f"the page stopped reporting; last: {page.last_read.sample if page.last_read else None!r}"
        )
        start_temp = self.board.system.kernel.soc_temperature_c()
        start_counters, start_hist = start.counters()

        time.sleep(WINDOW_SLEEP_SECONDS)
        ended_s, end = page.poll(
            until=lambda read: (
                read.sample is not None
                and (
                    read.sample["load"] != start.sample["load"]
                    or int(read.sample["el"]) >= start_counters["el"] + WINDOW_MS
                )
            ),
            within=END_WAIT_SECONDS,
            every=READ_PAUSE_SECONDS,
        )
        assert ended_s is not None, (
            f"the page stopped reporting within {END_WAIT_SECONDS} s; "
            f"last: {page.last_read.sample if page.last_read else None!r}"
        )
        if end.sample["load"] != start.sample["load"]:
            reloaded = "the page reloaded inside the window"
            self.record(validity=f"invalid: {reloaded}")
            pytest.fail(f"INVALID: {reloaded}")
        end_temp = self.board.system.kernel.soc_temperature_c()
        killed = proxy.killed()
        soak_samples = self.board.system.soak.samples_in(start.uptime, end.uptime)

        end_counters, end_hist = end.counters()
        hist = [after - before for before, after in zip(start_hist, end_hist, strict=False)]
        delta = {key: end_counters[key] - start_counters[key] for key in start_counters}
        stalls = sum(hist[STALL_FROM_BIN:])
        moving_share = delta["moving"] / delta["ticks"] if delta["ticks"] else 0.0
        problems = []
        if delta["changes"] != 0:
            problems.append("the page changed state inside the window")
        if not (page.shows_all_cards_live(start.sample) and page.shows_all_cards_live(end.sample)):
            problems.append("a read was not the applied page, on the board's own origin, cards live")
        if moving_share < MOTION_FLOOR:
            problems.append(f"too little motion seen in the window: {moving_share:.2f}")
        if killed:
            problems.append(f"the replay killed requests: {killed}")
        self.record(
            validity="valid" if not problems else f"invalid: {'; '.join(problems)}",
            stalls=stalls,
            window_ms=delta["el"],
            frames=delta["frames"],
            fps=round(delta["frames"] * 1000 / delta["isum"], 2) if delta["isum"] else None,
            hist=",".join(map(str, hist)),
            moving_share=round(moving_share, 3),
            probe_cost_ms=delta["cost"],
            load=end.sample["load"],
            uptime_start=start.uptime,
            uptime_end=end.uptime,
            soc_temp_start=start_temp,
            soc_temp_end=end_temp,
            soak_samples_in_window=len(soak_samples),
        )
        assert not problems, f"INVALID: {'; '.join(problems)}"
        assert stalls <= STALL_BOUND, (
            f"{stalls} frame stalls of {CUTOFF_MS} ms or more in {WINDOW_MS // 1000} s; TST009's bound is {STALL_BOUND}"
        )
