"""Target suite: the appliance's memory use stays under its bounds over a long run."""

import math

import pytest
from board_test import BoardTest, replaying
from replay import CARDS4_LIVE

# TST014's bound on memory in use, as a share of usable memory
USE_LIMIT = 0.80


class TestMemory(BoardTest):
    """The appliance's memory use stays under its bounds over a long run."""

    @replaying(CARDS4_LIVE)
    @pytest.mark.parametrize(
        ("period_s", "growth_limit_mb"),
        [
            pytest.param(30 * 60, 100, id="TST014"),
            # `--soak` adds a day's run on top, whose growth is not judged
            pytest.param(24 * 3600, math.inf, id="TST014-soak", marks=pytest.mark.soak),
        ],
    )
    def test_memory_over_a_long_run(self, period_s: int, growth_limit_mb: float) -> None:
        """TST014: run with the replayed page on the panel; memory in use stays bounded, and nothing is killed for it.

        Args:
            period_s: how long the run lasts.
            growth_limit_mb: the most memory in use may grow over the run, in MB.
        """
        self.record(requirement="TST014")
        self.board.app.run_behind_replay()
        self.board.app.install_probe()
        self.board.seconds_until(self.board.app.all_cards_live)

        use = self.board.system.memory.use_over(period_s)

        self.record(peak_use=round(use.peak_use, 3), growth_mb=round(use.growth_mb, 1), memory_kills=use.kills)
        assert not use.kills, f"a process was killed for memory at uptime {use.kills[0]:.0f} s"
        assert use.peak_use < USE_LIMIT, f"memory in use reached {use.peak_use:.1%} of usable; TST014's bound is 80%"
        assert use.growth_mb <= growth_limit_mb, (
            f"memory in use grew {use.growth_mb:.0f} MB over the run; TST014's bound is {growth_limit_mb} MB"
        )
