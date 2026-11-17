"""Target suite: a timezone set with timedatectl is the one the board reports local time in.

The set lands in an overlay on /etc whose upper layer is in /run, so the rootfs is never written.
"""

import pytest

_ZONES = {"Asia/Tokyo": "+0900", "Etc/UTC": "+0000"}
_RUN_DIR = "/run/tst026"


@pytest.fixture
def zone_in_run(request, board):
    """Overlay /etc with an upper layer in /run; return the original `/etc/localtime` link.

    timedated builds its own mount namespace when it starts, so it is stopped before the mount
    and the test's own `timedatectl` starts it inside the overlay; it is stopped again before the
    unmount. Each step's undo is registered once that step succeeds; teardown unmounts, asserts the
    overlay is gone and `/etc/localtime` points where it did, then removes the directory.
    """
    original = board.run("readlink /etc/localtime", check=True)[0][0].strip()
    board.run("modprobe overlay", check=True)
    board.run(f"mkdir -p {_RUN_DIR}/upper {_RUN_DIR}/work", check=True)
    request.addfinalizer(lambda: board.run(f"rm -rf {_RUN_DIR}", check=True))
    board.run("systemctl stop systemd-timedated", check=True)
    board.run(
        f"mount -t overlay tst026 -o lowerdir=/etc,upperdir={_RUN_DIR}/upper,workdir={_RUN_DIR}/work /etc",
        check=True,
    )

    def unmount():
        board.run("systemctl stop systemd-timedated")
        board.run("umount -l /etc", check=True)
        assert board.run("findmnt -n /etc")[2] != 0, "the /etc overlay is still mounted"
        restored = board.run("readlink /etc/localtime", check=True)[0][0].strip()
        assert restored == original, f"/etc/localtime is {restored}, expected {original}"

    request.addfinalizer(unmount)
    return original


def test_timezone_set_over_the_air(zone_in_run, board, record_property):
    """A zone with a different offset, set over ssh, is the zone `date` reports."""
    record_property("requirement", "TST026")
    current = board.run("date +%z", check=True)[0][0].strip()
    zone = next(z for z, offset in _ZONES.items() if offset != current)
    board.run(f"timedatectl set-timezone {zone}", check=True)
    reported = board.run("date '+%Y-%m-%dT%H:%M:%S%z %Z'", check=True)[0][0].strip()
    record_property("timezone_original", zone_in_run)
    record_property("timezone_set", zone)
    record_property("local_time_reported", reported)
    assert reported.split()[0][-5:] == _ZONES[zone], (
        f"{zone} set, board reports {reported}, expected offset {_ZONES[zone]}"
    )
