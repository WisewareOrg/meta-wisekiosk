"""The kiosk-soak sampler: its timer, and the log it keeps of the board's memory and processes."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from board import Board

_LOG_PATH = "/data/kiosk-soak.log"
# more of kiosk-soak's samples than TST009's window spans
_WINDOW_TAIL_LINES = 20


class Soak:
    """kiosk-soak on the board: one sample of memory and processes every five minutes, kept in its log."""

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board

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
        stdout, _stderr, _returncode = self._board.run(
            f"cut -c1-8 /proc/sys/kernel/random/boot_id; tail -n {_WINDOW_TAIL_LINES} {_LOG_PATH} 2>/dev/null; true"
        )
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
