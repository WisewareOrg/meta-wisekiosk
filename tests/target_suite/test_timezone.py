"""Target suite: a timezone set with timedatectl is the one the board reports local time in.

The set lands in an overlay on /etc whose upper layer is in /run, so the rootfs is never written.
"""

from collections.abc import Callable

import pytest
from board import Board

_ZONES = {"Asia/Tokyo": "+0900", "Etc/UTC": "+0000"}
_RUN_DIR = "/run/tst026"


@pytest.fixture
def zone_in_run(request: pytest.FixtureRequest, board: Board) -> str:
    """Overlay /etc with an upper layer in /run; return the original `/etc/localtime` link.

    First clears an overlay and `/run/tst026` that a dead run left behind.

    timedated builds its own mount namespace when it starts, so it is stopped before the mount
    and the test's own `timedatectl` starts it inside the overlay; it is stopped again before the
    unmount. Each step's undo is registered once that step succeeds; teardown unmounts, asserts the
    overlay is gone and `/etc/localtime` points where it did, then removes the directory.

    Args:
        request: registers each step's undo.
        board: the board under test, whose /etc is overlaid.

    Returns:
        The link `/etc/localtime` held before the overlay.

    Raises:
        AssertionError: a step on the board fails, or the board is not restored at teardown.
    """
    board.run("while findmnt -n /etc >/dev/null; do umount -l /etc || exit 1; done", check=True)
    board.run(f"rm -rf {_RUN_DIR}", check=True)
    original = board.read("readlink /etc/localtime")
    board.run("modprobe overlay", check=True)
    board.run(f"mkdir -p {_RUN_DIR}/upper {_RUN_DIR}/work", check=True)
    request.addfinalizer(lambda: board.run(f"rm -rf {_RUN_DIR}", check=True))
    board.run("systemctl stop systemd-timedated", check=True)
    board.run(
        f"mount -t overlay tst026 -o lowerdir=/etc,upperdir={_RUN_DIR}/upper,workdir={_RUN_DIR}/work /etc",
        check=True,
    )

    def unmount() -> None:
        """Stop timedated, remove the overlay and assert `/etc/localtime` is as it was.

        Raises:
            AssertionError: the overlay is still mounted, or `/etc/localtime` points elsewhere.
        """
        board.run("systemctl stop systemd-timedated")
        board.run("umount -l /etc", check=True)
        assert board.run("findmnt -n /etc")[2] != 0, "the /etc overlay is still mounted"
        restored = board.read("readlink /etc/localtime")
        assert restored == original, f"/etc/localtime is {restored}, expected {original}"

    request.addfinalizer(unmount)
    return original


def test_timezone_set_over_the_air(
    zone_in_run: str, board: Board, record_property: Callable[[str, object], None]
) -> None:
    """A zone with a different offset, set over ssh, is the zone `date` reports.

    Args:
        zone_in_run: the original `/etc/localtime` link, with /etc overlaid for the test.
        board: the board under test, whose timezone is set.
        record_property: records the requirement and the zones and time reported.

    Raises:
        AssertionError: the board's reported offset is not the one of the zone set.
    """
    record_property("requirement", "TST026")
    current = board.read("date +%z")
    zone = next(z for z, offset in _ZONES.items() if offset != current)
    board.run(f"timedatectl set-timezone {zone}", check=True)
    reported = board.read("date '+%Y-%m-%dT%H:%M:%S%z %Z'")
    record_property("timezone_original", zone_in_run)
    record_property("timezone_set", zone)
    record_property("local_time_reported", reported)
    assert reported.split()[0][-5:] == _ZONES[zone], (
        f"{zone} set, board reports {reported}, expected offset {_ZONES[zone]}"
    )
