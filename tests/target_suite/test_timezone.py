"""Target suite: a timezone set with timedatectl is the one the board reports local time in.

The set lands in an overlay on /etc whose upper layer is in /run, so the rootfs is never written.
"""

from board_test import BoardTest

_ZONES = {"Asia/Tokyo": "+0900", "Etc/UTC": "+0000"}


class TestTimezone(BoardTest):
    """A time zone set over the air is the one the board reports local time in."""

    def test_timezone_set_over_the_air(self) -> None:
        """TST026: a zone with a different offset, set over ssh, is the zone `date` reports."""
        timezone = self.board.system.timezone
        original = timezone.overlay_etc()
        self.record(requirement="TST026")
        zone = next(zone for zone, offset in _ZONES.items() if offset != timezone.utc_offset())

        timezone.set(zone)
        reported = timezone.local_time()

        self.record(timezone_original=original, timezone_set=zone, local_time_reported=reported)
        assert reported.split()[0][-5:] == _ZONES[zone], (
            f"{zone} set, board reports {reported}, expected offset {_ZONES[zone]}"
        )
