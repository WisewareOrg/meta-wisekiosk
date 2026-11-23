"""The board's memory over a long run: kiosk-soak's samples of it, and the kernel's record of what it killed."""

import itertools
import math
import re
from typing import TYPE_CHECKING, NamedTuple

from tenacity import Retrying, retry_if_result, stop_after_delay

from board.part import Part, invalid_if

if TYPE_CHECKING:
    from wisebench.proxy import Proxy

_OOM = re.compile(r"^\[\s*(\d+\.\d+)\].*(?:Out of memory|deadlocked on memory)")
_SOAK_LOG = "/data/kiosk-soak.log"
# kiosk-soak.timer's OnUnitActiveSec, and kiosk-soak.sh's own gap rule, as its --summary applies it
_SOAK_INTERVAL_SECONDS = 300
_SOAK_MAX_GAP_SECONDS = 450
# lines read beyond one per interval, so a period's first and last samples are in the tail
_SOAK_TAIL_MARGIN = 4
# how often a long sleep reads the boot, so a restart ends it early
_BOOT_CHECK_SECONDS = 600


class MemoryUse(NamedTuple):
    """The memory the board used over a run, what the kernel killed for memory, and what unsettled the run.

    Attributes:
        kills: the board uptime of each process killed for memory.
        peak_use: the most memory in use at any sample, as a share of usable memory; None if kiosk-soak's
            samples are unreadable.
        growth_mb: the growth in memory in use from the run's start to its end, in MB; None if the board
            restarted, so the run has no end.
        unsettled: what kept the run from being steady, each in a few words; empty for a steady run.
    """

    kills: list[float]
    peak_use: float | None
    growth_mb: float | None
    unsettled: list[str]

    def confirm_readable(self) -> None:
        """Fail the check as invalid if kiosk-soak's samples are unreadable, so no peak could be judged."""
        with invalid_if("kiosk-soak's samples are unreadable"):
            assert self.peak_use is not None

    def confirm_steady(self, replay: "Proxy") -> None:
        """Fail the check as invalid unless the run was steady, its replay included, so its growth means something.

        Args:
            replay: the proxy the backend ran behind.
        """
        unsettled = [*self.unsettled, *(["the replay killed a request"] if replay.killed() else [])]
        with invalid_if(f"the run was not steady: {'; '.join(unsettled)}"):
            assert not unsettled


class Memory(Part):
    """The board's memory: in use is MemTotal less MemAvailable; usable is MemTotal."""

    def use_over(self, seconds: float) -> MemoryUse:
        """Run the board for `seconds` with kiosk-soak sampling its memory every five minutes, and measure it.

        Reads after the run retry through a dropped session for `Board.READ_RETRY_SECONDS`. Kills are read
        from this boot's kernel log, or after a restart from the boot before's and pstore's.

        Args:
            seconds: how long the run lasts.

        Returns:
            What the run used, what was killed, and what unsettled the run: the kernel's log unreadable,
            the board restarting, a sampling gap, the browser or the backend restarting, or the page
            reloading or changing state.
        """
        board = self._board
        retry_for = board.READ_RETRY_SECONDS
        self._start_sampler()
        boot = board.boot_id(retry_for=retry_for)
        backend = board.app.backend.main_pid(retry_for=retry_for)
        page = board.wait_for(board.app.on_panel_report)
        start = board.uptime_s(retry_for=retry_for)
        in_use_before = self._in_use_kb()

        restarted = self._sleep_watching_boot(boot, seconds)
        end = math.inf if restarted else board.uptime_s(retry_for=retry_for)
        samples = self._samples(boot, start, end, seconds)
        kills, kernel_log_read = self._kills(start, previous_boot=restarted)
        usable_mb = self._meminfo_kb()["MemTotal"] / 1024
        available = [float(sample["memavail"]) for sample in samples if "memavail" in sample]
        readable = bool(samples) and len(available) == len(samples) and all(0 <= mb <= usable_mb for mb in available)
        peak_use = max(1 - mb / usable_mb for mb in available) if readable else None
        unsettled = [] if kernel_log_read else ["the kernel's log is unreadable"]
        if restarted:
            return MemoryUse(kills, peak_use, None, [*unsettled, "the board restarted"])
        edges = [start, *(float(sample["up"]) for sample in samples), end]
        if max(b - a for a, b in itertools.pairwise(edges)) > _SOAK_MAX_GAP_SECONDS:
            unsettled.append("a sampling gap")
        if len(browsers := {sample.get("pid") for sample in samples}) != 1 or not browsers.isdisjoint({"none", None}):
            unsettled.append("the browser restarted, or was not running")
        if board.app.backend.main_pid(retry_for=retry_for) != backend:
            unsettled.append("the backend restarted")
        now = board.app.report()
        if now is None or any(now.get(key) != page[key] for key in ("load", "changes", "cards")):
            unsettled.append("the page reloaded or changed state")
        return MemoryUse(kills, peak_use, (self._in_use_kb() - in_use_before) / 1024, unsettled)

    def _start_sampler(self) -> None:
        """Start kiosk-soak's timer; when the test ends it is stopped again, unless it was already running."""
        if self._board.run("systemctl is-active kiosk-soak.timer").returncode != 0:
            self._board.cleanup.callback(self._board.run, "systemctl stop kiosk-soak.timer", check=True)
        self._board.run("systemctl start kiosk-soak.timer", check=True)

    def _meminfo_kb(self) -> dict[str, int]:
        """Read `/proc/meminfo`.

        Returns:
            Each field in kB, by name.
        """
        lines = self._board.run("cat /proc/meminfo", check=True, retry_for=self._board.READ_RETRY_SECONDS).stdout
        return {line.split(":")[0]: int(line.split()[1]) for line in lines if ":" in line}

    def _in_use_kb(self) -> int:
        """Read the memory in use.

        Returns:
            MemTotal less MemAvailable, in kB.
        """
        meminfo = self._meminfo_kb()
        return meminfo["MemTotal"] - meminfo["MemAvailable"]

    def _sleep_watching_boot(self, boot: str, seconds: float) -> bool:
        """Sleep out `seconds`, reading the boot now, every 600 s and at the end, and end early if it booted again.

        Args:
            boot: the boot the sleep starts in.
            seconds: how long to sleep.

        Returns:
            Whether the board booted again.
        """
        return Retrying(
            stop=stop_after_delay(seconds),
            wait=lambda state: min(_BOOT_CHECK_SECONDS, max(0.0, seconds - state.seconds_since_start)),
            retry=retry_if_result(lambda restarted: not restarted),
            retry_error_callback=lambda state: state.outcome.result(),
        )(lambda: self._board.boot_id(retry_for=self._board.READ_RETRY_SECONDS) != boot)

    def _samples(self, boot: str, start: float, end: float, seconds: float) -> list[dict[str, str]]:
        """Read kiosk-soak's samples from the boot `boot` that fall inside an uptime span.

        Args:
            boot: the boot, as `Board.boot_id` reads it.
            start: the span's first board uptime.
            end: the span's last board uptime; inf for no end.
            seconds: how long the span lasts at most, which sizes the read.

        Returns:
            Each sample's fields, by name.
        """
        lines = self._board.run(
            f"tail -n {int(seconds // _SOAK_INTERVAL_SECONDS) + _SOAK_TAIL_MARGIN} {_SOAK_LOG} 2>/dev/null; true",
            retry_for=self._board.READ_RETRY_SECONDS,
        ).stdout
        samples = [dict(token.split("=", 1) for token in line.split() if "=" in token) for line in lines]
        return [
            sample
            for sample in samples
            if sample.get("boot") == boot[:8] and "up" in sample and start <= float(sample["up"]) <= end
        ]

    def _kills(self, since: float, previous_boot: bool) -> tuple[list[float], bool]:
        """Read the kernel's log for processes killed for memory, at or after the uptime `since`.

        The previous boot's is read from the journal, and from the console tail pstore kept of it.

        Args:
            since: the uptime from which a kill counts.
            previous_boot: read the boot before this one, not this one.

        Returns:
            The board uptime of each kill, and whether every read of the log succeeded.
        """
        reads = [f"journalctl -k {'-b -1' if previous_boot else '-b'} -o short-monotonic --no-pager"]
        if previous_boot:
            reads.append(
                'grep -q " /sys/fs/pstore " /proc/mounts || mount -t pstore pstore /sys/fs/pstore; '
                "cat /sys/fs/pstore/console-ramoops-0"
            )
        results = [self._board.run(read, retry_for=self._board.READ_RETRY_SECONDS) for read in reads]
        lines = [line for result in results for line in result.stdout]
        kills = {float(match[1]) for line in lines if (match := _OOM.match(line)) and float(match[1]) >= since}
        return sorted(kills), all(result.returncode == 0 for result in results)
