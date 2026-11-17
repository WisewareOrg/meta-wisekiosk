"""Target suite: a timezone set with timedatectl is the one the board reports local time in."""

import pytest

_ZONES = {"Asia/Tokyo": "+0900", "Etc/UTC": "+0000"}


@pytest.fixture
def restore_timezone(board):
    """Yield the board's timezone; at teardown set it back and check the read-back."""
    original = board.run("timedatectl show -p Timezone --value", check=True)[0][0].strip()
    try:
        yield original
    finally:
        board.run(f"timedatectl set-timezone {original}", check=True)
        restored = board.run("timedatectl show -p Timezone --value", check=True)[0][0].strip()
        assert restored == original, f"timezone restored to {restored}, expected {original}"


def test_timezone_set_over_the_air(restore_timezone, board, record_property):
    """A zone with a different offset, set over ssh, is the zone `date` reports."""
    record_property("requirement", "TST026")
    current = board.run("date +%z", check=True)[0][0].strip()
    zone = next(z for z, offset in _ZONES.items() if offset != current)
    board.run(f"timedatectl set-timezone {zone}", check=True)
    reported = board.run("date '+%Y-%m-%dT%H:%M:%S%z %Z'", check=True)[0][0].strip()
    record_property("timezone_original", restore_timezone)
    record_property("timezone_set", zone)
    record_property("local_time_reported", reported)
    assert reported.split()[0][-5:] == _ZONES[zone], (
        f"{zone} set, board reports {reported}, expected offset {_ZONES[zone]}"
    )
