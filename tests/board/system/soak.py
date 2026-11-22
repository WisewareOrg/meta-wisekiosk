"""The kiosk-soak sampler: its timer, and the log it keeps of the board's memory and processes."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from board import Board

_LOG_PATH = "/data/kiosk-soak.log"
# more of kiosk-soak's samples than TST009's window spans
_WINDOW_TAIL_LINES = 20
# kiosk-soak.timer's OnUnitActiveSec
_INTERVAL_SECONDS = 300
# lines read beyond one per interval, so a period's first and last samples are in the tail
_TAIL_MARGIN = 4


class Soak:
    """kiosk-soak on the board: one sample of memory and processes every five minutes, kept in its log.

    Attributes:
        MAX_GAP_SECONDS: kiosk-soak.sh's own gap rule, as its --summary applies it.
    """

    MAX_GAP_SECONDS = 450

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board

    def start_sampler(self) -> bool:
        """Start kiosk-soak's timer; when the test ends it is stopped again, unless it was already running.

        Returns:
            Whether the timer was already active.
        """
        was_active = self._board.run("systemctl is-active kiosk-soak.timer").returncode == 0
        if not was_active:
            self._board.cleanup.callback(self._board.run, "systemctl stop kiosk-soak.timer", check=True)
        self._board.run("systemctl start kiosk-soak.timer", check=True)
        return was_active

    def samples(self, boot: str, start: float, end: float, period: float) -> list[dict[str, str]]:
        """Read kiosk-soak's samples from the boot `boot` that fall inside an uptime span.

        Reads as many of the log's last lines as `period` covers, retrying through a dropped session
        for `Board.READ_RETRY_SECONDS` and raising the board's last error once that runs out.

        Args:
            boot: the boot, as `Board.BOOT_ID_CMD` prints it.
            start: the span's first board uptime, in seconds.
            end: the span's last board uptime, in seconds; inf for no end.
            period: the seconds the span covers at most, which sizes the read.

        Returns:
            Each sample's fields, by name.
        """
        stdout = self._board.run(
            f"tail -n {period // _INTERVAL_SECONDS + _TAIL_MARGIN} {_LOG_PATH} 2>/dev/null; true",
            retry_for=self._board.READ_RETRY_SECONDS,
        ).stdout
        samples = [self._fields(line) for line in stdout]
        return [sample for sample in samples if sample.get("boot") == boot[:8] and start <= float(sample["up"]) <= end]

    @staticmethod
    def left_a_gap(samples: list[dict[str, str]], start: float, end: float) -> bool:
        """Whether kiosk-soak left a gap over its own limit in a span: no sample, or two too far apart.

        The span's ends count as samples.

        Args:
            samples: the span's samples, in order.
            start: the span's first board uptime, in seconds.
            end: the span's last board uptime, in seconds.

        Returns:
            True if the span holds no sample, or a gap over `MAX_GAP_SECONDS`.
        """
        edges = [start, *(float(sample["up"]) for sample in samples), end]
        return not samples or max(b - a for a, b in zip(edges, edges[1:], strict=False)) > Soak.MAX_GAP_SECONDS

    def samples_in(self, start: float, end: float) -> list[dict[str, str]]:
        """Read kiosk-soak's samples from this boot that fall inside an uptime span.

        Reads the log's last lines, which cover more than a window, and this boot's id, in one
        command.

        Args:
            start: the span's first board uptime, in seconds.
            end: the span's last board uptime, in seconds.

        Returns:
            Each sample's fields, by name.
        """
        stdout = self._board.run(
            f"cut -c1-8 /proc/sys/kernel/random/boot_id; tail -n {_WINDOW_TAIL_LINES} {_LOG_PATH} 2>/dev/null; true"
        ).stdout
        boot = stdout[0]
        samples = [self._fields(line) for line in stdout[1:]]
        return [sample for sample in samples if sample.get("boot") == boot and start <= float(sample["up"]) <= end]

    @staticmethod
    def _fields(line: str) -> dict[str, str]:
        """One log line's `name=value` fields.

        Args:
            line: the log line.

        Returns:
            The fields, by name.
        """
        return dict(token.split("=", 1) for token in line.split() if "=" in token)
