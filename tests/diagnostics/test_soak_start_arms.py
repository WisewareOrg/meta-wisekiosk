"""Diagnostics: does a soak start inside a full-slot write make PID 1 miss the watchdog's feed, and not without?

Runs `PAIRS` pairs of installs of the candidate's own bundle, strictly in turn, arm A then arm B, with no
reboot between (RAUC writes the slot the board did not boot, so each install writes the whole slot) and
one 1 Hz reader (`test_install_watchdog_margin.READER`) through all of it:

- arm A: the case starts `kiosk-soak.service` every `EVERY_S` seconds while RAUC writes;
- arm B: the case starts nothing. The timer is not stopped, so B first waits, if it must, until the whole
  install fits before the timer's next start; a B write that still overlapped a start is reclassified
  "natural" afterwards.

The arm of each install is decided by the journal's `Starting` lines against the write, and both the
planned and the journal's arm are recorded. It records every install's readings and gives no verdict. It
stops, recording why, on: a reset (the boot id changed: that is the result, and nothing more is installed),
an install that failed, or a write under `MIN_FULL_WRITE_MIB` (the full-slot build did not take). It
waits until the board has been up `MIN_UPTIME_S` first, and fails only when no `timeleft` was read.

Outside the regression suite: run by hand through the bench driver, last in its session.
"""

import subprocess
import threading
import time
from collections.abc import Callable

import pytest
from board import Board
from board.part import invalid_if
from test_install_watchdog_margin import (
    CANDIDATE_BUNDLE,
    EVERY_S,
    GAP_S,
    LOW_TIMELEFT_S,
    MIN_UPTIME_S,
    READER,
    SECTOR_BYTES,
    SECTORS_WRITTEN,
    SOAK_LINE,
    STATS,
    Sample,
    _read,
    _uptime_at,
)

PAIRS = 4
MIN_FULL_WRITE_MIB = 1900
# arming about 55 s, the write about 190 s, and the end
INSTALL_SPAN_S = 280
AFTER_START_S = 10
SOAK_TIMER = "kiosk-soak.timer"


def _wait_for_a_clear_span(board: Board) -> float:
    """Wait, if need be, until a whole install fits before the soak timer's next start.

    Args:
        board: the board under test.

    Returns:
        The seconds waited.
    """
    next_start = float(board.run(f"systemctl show -p NextElapseUSecMonotonic --value {SOAK_TIMER}", check=True).text)
    left = next_start / 1e6 - board.uptime_s()
    wait = left + AFTER_START_S if left < INSTALL_SPAN_S else 0.0
    time.sleep(max(0.0, wait))
    return max(0.0, wait)


def _journal_starts(board: Board, boot: str) -> list[float]:
    """The uptimes of the soak unit's `Starting` lines in `boot`.

    Args:
        board: the board under test.
        boot: the boot id, with or without dashes.

    Returns:
        The uptimes, in seconds.
    """
    lines = board.run(
        f"journalctl -b {boot.replace('-', '')} -u kiosk-soak.service -o short-monotonic --no-pager", check=True
    ).stdout
    return [float(m["up"]) for line in lines if (m := SOAK_LINE.match(line))]


def _soak_starter(board: Board, log: list[str]) -> Callable[[], None]:
    """Make the hook that starts the soak unit and notes whether it worked.

    Args:
        board: the board under test.
        log: where each start's outcome goes.

    Returns:
        The hook, which does not raise.
    """

    def start_soak() -> None:
        """Start the soak unit and note whether it worked."""
        try:
            board.run("systemctl start --no-block kiosk-soak.service", check=True)
            log.append("ok")
        except (AssertionError, *Board.ERRORS) as error:
            log.append(f"failed: {type(error).__name__}")

    return start_soak


@pytest.mark.sends_update
def test_soak_start_arms(board: Board, record_property: Callable[[str, object], None]) -> None:
    """Install in turn with and without soak starts in the write, and record each install's watchdog reading.

    Args:
        board: the board under test.
        record_property: records each install's readings and the arm counts.
    """
    uptime = board.uptime_s()
    time.sleep(max(0.0, MIN_UPTIME_S - uptime))
    boot = board.boot_id()
    samples: list[Sample] = []
    reader = subprocess.Popen(
        [*board.fresh_ssh_argv("ServerAliveInterval=2"), READER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    collector = threading.Thread(target=_read, args=(reader, samples))
    collector.start()
    dips = {"start": 0, "none": 0, "natural": 0, "void": 0}
    counted = {"start": 0, "none": 0, "natural": 0, "void": 0}
    stopped = "all installs done"
    try:
        for number in range(1, 2 * PAIRS + 1):
            planned = "A" if number % 2 else "B"
            waited = _wait_for_a_clear_span(board) if planned == "B" else 0.0
            by_test: list[str] = []
            start_soak = _soak_starter(board, by_test)

            began = time.monotonic()
            watched = board.updates.install_watched(
                CANDIDATE_BUNDLE, start_soak if planned == "A" else (lambda: None), EVERY_S
            )
            finished = time.monotonic()
            key = f"i{number}.{planned}"
            window = [s for s in samples if began <= s.host <= finished]
            written = [
                int(m.group(1).split()[SECTORS_WRITTEN]) for m in map(STATS.search, watched.output.splitlines()) if m
            ]
            mib = (max(written) - min(written)) * SECTOR_BYTES / 2**20 if written else 0.0
            record_property(f"{key}.install_rc", watched.returncode)
            record_property(f"{key}.written_mib", mib)
            record_property(f"{key}.waited_s", waited)
            record_property(f"{key}.starts_by_test", "; ".join(by_test))
            record_property(f"{key}.samples", len(window))
            if window:
                low = [s for s in window if s.timeleft < LOW_TIMELEFT_S]
                lowest = min(window, key=lambda s: s.timeleft)
                record_property(f"{key}.timeleft_min", lowest.timeleft)
                record_property(f"{key}.timeleft_min_uptime", lowest.uptime)
                record_property(
                    f"{key}.low_samples",
                    "; ".join(f"{s.uptime:.0f}:{s.timeleft}:{s.pid1_state}:{s.wchan}" for s in low),
                )
                stamps = [began, *(s.host for s in window), finished]
                gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False) if b - a > GAP_S]
                record_property(f"{key}.gaps_over_2s", gaps)
            try:
                boot_now = board.boot_id()
            except Board.ERRORS:
                boot_now = None
            if boot_now != boot:
                record_property(f"{key}.boot_changed", True)
                stopped = f"install {number}: the boot id changed or could not be read: a reset is the result"
                break
            if watched.returncode != 0:
                stopped = f"install {number} failed (rc {watched.returncode})"
                break
            if mib < MIN_FULL_WRITE_MIB:
                stopped = f"install {number} wrote {mib:.0f} MiB: the full-slot build did not take, the run is void"
                break
            in_write = []
            if window and watched.write_began is not None and watched.write_ended is not None:
                write_from = _uptime_at(window, watched.write_began)
                write_to = _uptime_at(window, watched.write_ended)
                record_property(f"{key}.write_uptime", f"{write_from:.1f}-{write_to:.1f}")
                in_write = [t for t in _journal_starts(board, boot) if write_from <= t <= write_to]
            record_property(f"{key}.journal_starts_in_write", in_write)
            arm = ("start" if planned == "A" else "natural") if in_write else ("void" if planned == "A" else "none")
            record_property(f"{key}.arm_by_journal", arm)
            counted[arm] += 1
            dips[arm] += any(s.timeleft < LOW_TIMELEFT_S for s in window)
    finally:
        reader.terminate()
        collector.join()
        record_property("stopped", stopped)
        record_property("installs_by_arm", counted)
        record_property("installs_with_a_dip_by_arm", dips)
        record_property("samples", len(samples))

    with invalid_if("no timeleft could be read"):
        assert samples, "no sample"
