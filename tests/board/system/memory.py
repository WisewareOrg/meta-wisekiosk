"""The board's memory, and the kernel's record of processes it killed for memory."""

import re
from typing import NamedTuple

from board.part import Part

_OOM = re.compile(r"^\[\s*(\d+\.\d+)\].*(?:Out of memory|deadlocked on memory)")


class OomKills(NamedTuple):
    """The kernel's out-of-memory lines from one log.

    Attributes:
        returncode: the read's return code; nonzero means the log could not be read.
        uptimes: the board uptime of each out-of-memory line at or after the read's `since`.
    """

    returncode: int
    uptimes: list[float]


class Memory(Part):
    """The board's memory, and the kernel's out-of-memory record in this boot, the last, and pstore.

    Every read retries through a dropped session for `Board.READ_RETRY_SECONDS`, and raises the board's
    last error once that runs out.
    """

    def meminfo_kb(self) -> dict[str, int]:
        """Read `/proc/meminfo`.

        Returns:
            Each field in kB, by name.
        """
        stdout = self._board.run("cat /proc/meminfo", check=True, retry_for=self._board.READ_RETRY_SECONDS).stdout
        return {line.split(":")[0]: int(line.split()[1]) for line in stdout if ":" in line}

    def oom_kills_this_boot(self, since: float) -> OomKills:
        """Read this boot's kernel log for processes killed for memory.

        Args:
            since: the board uptime from which a kill counts.

        Returns:
            The read's return code and the kills' uptimes.
        """
        return self._kernel_log_kills("-b", since)

    def oom_kills_previous_boot(self, since: float) -> OomKills:
        """Read the previous boot's kernel log for processes killed for memory.

        Args:
            since: the previous boot's uptime from which a kill counts.

        Returns:
            The read's return code and the kills' uptimes.
        """
        return self._kernel_log_kills("-b -1", since)

    def oom_kills_in_pstore(self, since: float) -> OomKills:
        """Read the previous boot's kernel console tail in pstore for processes killed for memory.

        Mounts pstore first if it is not mounted.

        Args:
            since: the previous boot's uptime from which a kill counts.

        Returns:
            The read's return code and the kills' uptimes.
        """
        console = self._board.run(
            'grep -q " /sys/fs/pstore " /proc/mounts || mount -t pstore pstore /sys/fs/pstore; '
            "cat /sys/fs/pstore/console-ramoops-0",
            retry_for=self._board.READ_RETRY_SECONDS,
        )
        return OomKills(console.returncode, self._uptimes_since(console.stdout, since))

    def _kernel_log_kills(self, boot_flag: str, since: float) -> OomKills:
        """Read the kernel log of the boot `boot_flag` names for processes killed for memory.

        Args:
            boot_flag: `journalctl`'s boot selection.
            since: the board uptime from which a kill counts.

        Returns:
            The read's return code and the kills' uptimes.
        """
        journal = self._board.run(
            f"journalctl -k {boot_flag} -o short-monotonic --no-pager", retry_for=self._board.READ_RETRY_SECONDS
        )
        return OomKills(journal.returncode, self._uptimes_since(journal.stdout, since))

    @staticmethod
    def _uptimes_since(lines: list[str], since: float) -> list[float]:
        """The uptimes of the out-of-memory lines among `lines`, at or after `since`.

        Args:
            lines: kernel log lines, stamped with the uptime.
            since: the uptime from which a line counts.

        Returns:
            The uptimes, in log order.
        """
        found = [float(match.group(1)) for line in lines if (match := _OOM.match(line))]
        return [uptime for uptime in found if since <= uptime]
