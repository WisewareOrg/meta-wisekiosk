"""Target suite: the browser killed with nobody at the panel is back on the panel in time."""

from board_test import BoardTest

# TST001's bound
_BOUND_SECONDS = 45
# stop polling; past the bound, so the record still carries the time it took
_GIVE_UP_SECONDS = 120
_POLL_SECONDS = 0.5


class TestBrowserKilled(BoardTest):
    """The browser killed with nobody at the panel is back on the panel in time."""

    def test_browser_killed(self) -> None:
        """TST001 browser killed: SIGKILL the browser and time until the instance is on the panel again."""
        page = self.board.app.page
        self.record(probe_sha256=page.install_probe())
        self.record(requirement="TST001")
        _, before = page.wait_for_instance()

        killed_at = page.kill_browser()
        back_s, last = page.poll(
            until=lambda read: page.shows_instance(read.sample) and read.sample["nonce"] != before["nonce"],
            within=_GIVE_UP_SECONDS,
            every=_POLL_SECONDS,
        )

        # the board uptime of the first read showing the page back, so it overstates by up to one read
        recovered_s = round(last.uptime - killed_at, 1) if back_s is not None else None
        after = last.sample if last else None
        self.record(before=before, after=after, killed_at_uptime_s=killed_at, recovered_s=recovered_s)
        assert recovered_s is not None, (
            f"no sample on the panel carried a new nonce within {_GIVE_UP_SECONDS} s of the kill; "
            f"last sample: {after!r}"
        )
        assert recovered_s <= _BOUND_SECONDS, (
            f"back on the panel after {recovered_s} s; TST001's bound is {_BOUND_SECONDS} s"
        )
