"""Target suite: a time zone set over the air is the one the board reports local time in."""

from board_test import BoardTest

# two zones with different offsets, so one always differs from the board's
ZONES = {"Asia/Tokyo": "+0900", "Etc/UTC": "+0000"}


class TestTimezone(BoardTest):
    """A time zone set over the air is the one the board reports local time in."""

    def test_timezone_set_over_the_air(self) -> None:
        """TST026: set a zone unlike the board's current one; its local time is then in that zone."""
        self.record(requirement="TST026")
        self.board.system.overlay_etc()
        current = self.board.system.utc_offset()
        zone, offset = next((zone, offset) for zone, offset in ZONES.items() if offset != current)

        self.board.system.set_timezone(zone)
        reported = self.board.system.utc_offset()

        self.record(timezone_set=zone, utc_offset=reported)
        assert reported == offset, f"{zone} set, but the board's local time is at {reported}, not {offset}"
