"""Diagnostics: the appliance says why it last restarted, and the four causes read differently.

Resets the board four ways, in this order: a power cut, a restart, a kernel panic and a watchdog
bite. After each it reads the `kiosk-last-reset` line that `kiosk-journal-flush.service` prints in the new
boot (`last reset rsts=<status> console=<how the previous console ended>`). After the bite it reads the
lines of the three boots before it, named by their boot ids, and each must equal what was read in that boot;
the running boot's line carries a time within a day of the board's clock. `rsts` is recorded
and its power-on bit asserted: set after the cut, clear after each of the others. `console` is asserted,
and the bite is the only one among restart, panic and bite whose console read silent.

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

# PM_RSTS_HADPOR_SET in the Broadcom header: the chip's power-on-reset flag, bit 12 of its power-management
# status register.
POWER_ON = 0x1000
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


def _reset_line(board: Board, errors: list[str], boot: str = "0") -> ResetLine | None:
    """Read the `rsts` and `console` of a boot's `kiosk-last-reset` line.

    Args:
        board: the board under test.
        errors: collects the error of a read the board did not answer.
        boot: `journalctl -b`'s argument: 0 for the running boot, or a boot id.

    Returns:
        The line's fields; None if the boot has not logged the line yet, or the read got no answer.
    """
    cmd = f"journalctl -b {boot} -u kiosk-journal-flush.service -o cat --no-pager"
    try:
        found = LINE.search(board.run(cmd, check=True, timeout=60).text)
    except Board.ERRORS as error:
        errors.append(f"{type(error).__name__}: {error}")
        return None
    return ResetLine(found.group("rsts"), found.group("console")) if found else None


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
    seen = {}
    boot_ids = {}
    for cause, stimulus in stimuli.items():
        stimulus()
        errors: list[str] = []
        try:
            seen[cause] = board.wait_for(lambda errors=errors: _reset_line(board, errors))
        except AssertionError as gave_up:
            pytest.fail(f"{gave_up}; the last read error: {errors[-1] if errors else 'none'}", pytrace=False)
        boot_ids[cause] = board.boot_id().strip().replace("-", "")
        record_property(f"{cause}.rsts", seen[cause].rsts)
        record_property(f"{cause}.console", seen[cause].console)

    for cause in ("kernel panic", "restart", "power cut"):
        errors = []
        kept = _reset_line(board, errors, boot_ids[cause])
        assert kept == seen[cause], f"the {cause}'s boot read {seen[cause]}; the journal now gives {kept} {errors}"
    stamped = STAMPED_LINE.search(
        board.run("journalctl -b 0 -u kiosk-journal-flush.service -o short-unix --no-pager", check=True).text
    )
    assert stamped, "the running boot's line has no time in the journal"
    skew = abs(float(stamped.group("unix")) - float(board.run("date +%s", check=True).text.strip()))
    assert skew < CLOCK_TOLERANCE_SECONDS, (
        f"the line's time is {skew:.0f} s from the board's clock: written before the clock was restored"
    )
    for cause, read in seen.items():
        assert re.fullmatch(r"[0-9a-f]+", read.rsts), f"after the {cause} rsts read {read.rsts}, not hex"
    cut = seen["power cut"]
    assert int(cut.rsts, 16) & POWER_ON, (
        f"after the power cut rsts {cut.rsts} lacks the power-on bit: the bit is not where the header says, "
        "or the plug did not cut; the keeper cannot be judged"
    )
    assert cut.console in ("silent", "none"), f"after a power cut the console read {cut.console}"
    expected = {"restart": "restart", "kernel panic": "panic", "watchdog bite": "silent"}
    for cause, console in expected.items():
        read = seen[cause]
        assert not int(read.rsts, 16) & POWER_ON, (
            f"after the {cause} rsts {read.rsts} still has the power-on bit: the register accumulates "
            "across resets and the keeper separates nothing"
        )
        assert read.console == console, f"after a {cause} the console read {read.console}, not {console}"
