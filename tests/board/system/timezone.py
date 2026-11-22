"""The board's time zone, and the local time it reports in."""

from board.part import Part

_RUN_DIR = "/run/tst026"


class Timezone(Part):
    """The board's time zone, set through timedated, and the local time it reports."""

    def overlay_etc(self) -> str:
        """Overlay /etc with an upper layer in /run, so a zone set never writes the rootfs, until the test ends.

        First clears an overlay and `/run/tst026` that a dead run left behind. timedated builds its own
        mount namespace when it starts, so it is stopped before the mount, and the next `timedatectl`
        starts it inside the overlay. Each step's undo is registered once that step succeeds. When the
        test ends, timedated is stopped, /etc is unmounted, and the overlay is asserted gone with
        `/etc/localtime` pointing where it did; then the directory is removed.

        Returns:
            Where `/etc/localtime` pointed before the overlay.
        """
        board = self._board
        board.run("while findmnt -n /etc >/dev/null; do umount -l /etc || exit 1; done", check=True)
        board.run(f"rm -rf {_RUN_DIR}", check=True)
        original = board.run("readlink /etc/localtime", check=True).stdout[0].strip()
        board.run("modprobe overlay", check=True)
        board.run(f"mkdir -p {_RUN_DIR}/upper {_RUN_DIR}/work", check=True)
        board.cleanup.callback(board.run, f"rm -rf {_RUN_DIR}", check=True)
        board.run("systemctl stop systemd-timedated", check=True)
        board.run(
            f"mount -t overlay tst026 -o lowerdir=/etc,upperdir={_RUN_DIR}/upper,workdir={_RUN_DIR}/work /etc",
            check=True,
        )
        board.cleanup.callback(self._unmount_etc, original)
        return original

    def set(self, zone: str) -> None:
        """Set the time zone with `timedatectl`.

        Args:
            zone: the zone's name, e.g. `Asia/Tokyo`.
        """
        self._board.run(f"timedatectl set-timezone {zone}", check=True)

    def utc_offset(self) -> str:
        """Read the local time's offset from UTC, as `date +%z` prints it.

        Returns:
            The offset, e.g. `+0900`.
        """
        return self._board.run("date +%z", check=True).stdout[0].strip()

    def local_time(self) -> str:
        """Read the local time with its offset and zone.

        Returns:
            The time, as `date '+%Y-%m-%dT%H:%M:%S%z %Z'` prints it.
        """
        return self._board.run("date '+%Y-%m-%dT%H:%M:%S%z %Z'", check=True).stdout[0].strip()

    def _unmount_etc(self, original: str) -> None:
        """Stop timedated and unmount the /etc overlay; assert it is gone and `/etc/localtime` is as it was.

        Args:
            original: where `/etc/localtime` pointed before the overlay.
        """
        self._board.run("systemctl stop systemd-timedated")
        self._board.run("umount -l /etc", check=True)
        assert self._board.run("findmnt -n /etc").returncode != 0, "the /etc overlay is still mounted"
        restored = self._board.run("readlink /etc/localtime", check=True).stdout[0].strip()
        assert restored == original, f"/etc/localtime is {restored}, expected {original}"
