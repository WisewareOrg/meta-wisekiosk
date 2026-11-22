"""Target suite: a clock set wrong by days and persisted across a restart is corrected."""

import time

from board_test import BoardTest

# TST015's bound, in seconds of the board's uptime
_BOUND_SECONDS = 100
# the clock agrees when it is this close to the host's
_AGREE_SECONDS = 5
_POLL_SECONDS = 2
# the stimulus: three days back; timesyncd's first entry must show it to within a day
_SKEW_SECONDS = 3 * 24 * 3600
_SKEW_TOLERANCE_SECONDS = 24 * 3600


class TestClock(BoardTest):
    """The board's clock is corrected after being set wrong and persisted across a restart."""

    def test_clock_set_wrong(self) -> None:
        """TST015 clock set wrong: the clock agrees with the host's within `_BOUND_SECONDS` of uptime.

        A clock that agrees counts only if this boot's first timesyncd entry carries the clock the
        stimulus set, to within a day; otherwise the check is invalid.
        """
        self.record(requirement="TST015")
        clock = self.board.system.clock
        clock.stop_sync()
        clock.set(int(time.time()) - _SKEW_SECONDS)

        self.board.reboot()
        self.board.poll(
            clock.read,
            until=lambda reading: abs(reading.offset_s) <= _AGREE_SECONDS or reading.uptime_s > _BOUND_SECONDS,
            within=_BOUND_SECONDS,
            every=_POLL_SECONDS,
        )
        reading = clock.last_reading
        behind_s = clock.first_sync_offset_s()
        print(clock.sync_journal())

        assert reading is not None, "the board's clock could not be read after the restart"
        self.record(clock_corrected_seconds=reading.uptime_s)
        assert abs(reading.offset_s) <= _AGREE_SECONDS, (
            f"clock still {reading.offset_s:.0f}s off the network's time at uptime {reading.uptime_s:.0f}s, "
            f"bound {_BOUND_SECONDS}s"
        )
        assert behind_s is not None, "INVALID CHECK, not an appliance failure: timesyncd logged nothing this boot"
        assert abs(behind_s - _SKEW_SECONDS) < _SKEW_TOLERANCE_SECONDS, (
            f"INVALID CHECK, not an appliance failure: timesyncd's first entry was {behind_s:.0f}s "
            f"behind the host, not the {_SKEW_SECONDS}s the stimulus set"
        )
        assert reading.uptime_s <= _BOUND_SECONDS, (
            f"clock agreed only at uptime {reading.uptime_s:.0f}s, bound {_BOUND_SECONDS}s"
        )
