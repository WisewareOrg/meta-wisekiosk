"""Diagnostics: the appliance says why it last restarted, and the four causes read differently.

Resets the board four ways, in this order: a power cut, a restart, a kernel panic and a watchdog
bite. After each it reads the `kiosk-last-reset` line that `kiosk-journal-flush.service` prints in the new
boot (`last reset rsts=<status> console=<how the previous console ended>`). After the bite, the kernel
messages of all four boots, read by boot id, must contain the kernel's `Linux version` line, which a journal
at its cap loses with the boot's first seconds. Then the `kiosk-last-reset` lines of the three boots before
the last, read by boot id, must each equal what was read in that boot; the running boot's line carries a time
within a day of the board's clock. `rsts` is recorded and judged by its watchdog-full-reset bit, which
separates the cut from the three resets that follow it: clear after the cut, set after the restart, the
panic and the bite. The power-on bit is asserted after the cut and only recorded after the others, for the
reason `kiosk-last-reset`'s header gives. `console` is asserted, and the bite is the only one
among restart, panic and bite whose console read silent.

The bite freezes PID 1's cgroup, so nothing feeds the 14 s hardware watchdog; if it does not bite, a
detached shell thaws the cgroup after 60 s. Nothing is written to disk. Bench only.

Outside the regression suite, run through the bench driver:

    bench test <ref> -- tests/diagnostics -k restart_cause -rP
"""

import re
from collections.abc import Callable
from typing import NamedTuple

import pytest
from board import Board

# The power-on bit of rsts, as `kiosk-last-reset`'s header defines it.
POWER_ON = 0x1000
# The watchdog-full-reset bit of rsts, as `kiosk-last-reset`'s header defines it.
WATCHDOG_FULL = 0x20
LINE = re.compile(r"last reset rsts=(?P<rsts>\S+) console=(?P<console>\w+)")
STAMPED_LINE = re.compile(r"^(?P<unix>\d+\.\d+) .*last reset rsts=", re.MULTILINE)
CLOCK_TOLERANCE_SECONDS = 86400


class ResetLine(NamedTuple):
    """What a boot's `kiosk-last-reset` line says about the reset before it.

    Attributes:
        rsts: the firmware's reset status.
        console: how the previous boot's console ended.
    """

    rsts: str
    console: str


def _reset_line(board: Board, boot: str = "0") -> ResetLine | None:
    """Read the `rsts` and `console` of a boot's `kiosk-last-reset` line.

    Args:
        board: the board under test.
        boot: `journalctl -b`'s argument: 0 for the running boot, or a boot id.

    Returns:
        The line's fields; None if the boot has not logged the line.
    """
    cmd = f"journalctl -b {boot} -u kiosk-journal-flush.service -o cat --no-pager"
    found = LINE.search(board.run(cmd, check=True, timeout=60).text)
    return ResetLine(found.group("rsts"), found.group("console")) if found else None


def _kernel_log(board: Board, boot: str) -> str:
    """Read a boot's kernel messages with their monotonic times.

    Args:
        board: the board under test.
        boot: a boot id, as `journalctl -b` takes it.

    Returns:
        The kernel messages.
    """
    cmd = f"journalctl -b {boot} -k -o short-monotonic --no-pager"
    return board.run(cmd, check=True, timeout=60).text


class _RunningBootLine:
    """The running boot's line, read until it is logged, keeping the last error of a read the board did not answer.

    Attributes:
        last_error: the last such error, empty if none.
    """

    last_error: str

    def __init__(self, board: Board) -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board
        self.last_error = ""

    def read(self) -> ResetLine | None:
        """Read the line once.

        Returns:
            The line; None if it is not logged yet or the read got no answer.
        """
        try:
            return _reset_line(self._board)
        except Board.ERRORS as error:
            self.last_error = f"{type(error).__name__}: {error}"
            return None


def test_restart_cause(board: Board, record_property: Callable[[str, object], None]) -> None:
    """The line of the boot after each reset names how the previous boot's console ended.

    Args:
        board: the board under test.
        record_property: records each cause's two values.
    """
    stimuli = {
        "power cut": board.cut_power,
        "restart": board.restart,
        "kernel panic": board.crash_kernel,
        "watchdog bite": board.starve_watchdog,
    }
    running = _RunningBootLine(board)
    seen = {}
    boot_ids = {}
    for cause, stimulus in stimuli.items():
        stimulus()
        try:
            seen[cause] = board.wait_for(running.read)
        except AssertionError as gave_up:
            pytest.fail(f"{gave_up}; the last read error: {running.last_error or 'none'}", pytrace=False)
        boot_ids[cause] = board.boot_id().strip().replace("-", "")
        record_property(f"{cause}.rsts", seen[cause].rsts)
        record_property(f"{cause}.console", seen[cause].console)
    kernel_logs = {cause: _kernel_log(board, boot) for cause, boot in boot_ids.items()}
    kept = {cause: _reset_line(board, boot_ids[cause]) for cause in ("kernel panic", "restart", "power cut")}
    stamped = STAMPED_LINE.search(
        board.run("journalctl -b 0 -u kiosk-journal-flush.service -o short-unix --no-pager", check=True).text
    )
    skew = (
        abs(float(stamped.group("unix")) - float(board.run("date +%s", check=True).text.strip())) if stamped else None
    )

    assert_resets(seen)
    for cause, kernel in kernel_logs.items():
        first = kernel.splitlines()[0] if kernel.strip() else "no entries"
        assert "Linux version" in kernel, (
            f"the {cause}'s boot {boot_ids[cause]} does not start with the kernel's version line; "
            f"its first entry reads: {first}"
        )
    for cause, line in kept.items():
        assert line == seen[cause], f"the {cause}'s boot read {seen[cause]}; the journal now gives {line}"
    assert skew is not None, "the running boot's line has no time in the journal"
    assert skew < CLOCK_TOLERANCE_SECONDS, (
        f"the line's time is {skew:.0f} s from the board's clock: written before the clock was restored"
    )


def assert_resets(seen: dict[str, ResetLine]) -> None:
    """Assert what the four causes' lines must say.

    Args:
        seen: each cause's line, keyed by "power cut", "restart", "kernel panic" and "watchdog bite".
    """
    for cause, read in seen.items():
        assert re.fullmatch(r"[0-9a-f]+", read.rsts), f"after the {cause} rsts read {read.rsts}, not hex"
    cut = seen["power cut"]
    assert int(cut.rsts, 16) & POWER_ON, (
        f"after the power cut rsts {cut.rsts} lacks the power-on bit: the bit is not where the header says, "
        "or the plug did not cut; the watchdog-full-reset bit cannot be judged"
    )
    assert not int(cut.rsts, 16) & WATCHDOG_FULL, (
        f"after the power cut rsts {cut.rsts} has the watchdog-full-reset bit: the bit separates nothing"
    )
    assert cut.console in ("silent", "none"), f"after a power cut the console read {cut.console}"
    expected = {"restart": "restart", "kernel panic": "panic", "watchdog bite": "silent"}
    for cause, console in expected.items():
        read = seen[cause]
        assert int(read.rsts, 16) & WATCHDOG_FULL, (
            f"after the {cause} rsts {read.rsts} lacks the watchdog-full-reset bit: the bit is not where the "
            "header says, or the bit separates nothing"
        )
        assert read.console == console, f"after a {cause} the console read {read.console}, not {console}"
