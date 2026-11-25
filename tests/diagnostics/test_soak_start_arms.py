"""Diagnostics: does a soak start inside a full-slot write make PID 1 miss the watchdog's feed, and not without?

Runs the installs of `ARMS` in turn, one after another with no reboot between (RAUC writes the slot the
board did not boot, so each install writes the whole slot), with one 1 Hz reader (`READER`) through all of
it. The case starts nothing:

- arm A: the install begins `A_LEAD_S` seconds before the timer's next start (`NextElapseUSecMonotonic`),
  so the timer's own start falls late in the write;
- arm B: the install begins `AFTER_START_S` seconds after a start, so that arming and write end before the
  next one. A B write that overlapped a start anyway is reclassified "natural".

The arm of each install is decided by the journal's `Starting` lines against the write, and both the
planned and the journal's arm are recorded, each install by its ordinal. It records every install's readings and
gives no verdict. It stops, recording why, on: the clock (`CUT_AFTER_S`), an under-voltage reading in an
install's stats, the first install's span, a reset (the boot id changed: that is the result, and nothing more
is installed), an install that failed, or a write under `MIN_FULL_WRITE_MIB` (the full-slot build did not take).
It waits until the board has been up `UP_AT_START_S` first, and fails only when no `timeleft` was read.

The first A and the first B are the only installs alike to the old records, so they are printed alone;
the rest pool by arm, with the repeats' difference stated beside.

Outside the regression suite: run by hand through the bench driver, last in its session.
"""

import contextlib
import re
import subprocess
import threading
import time
from collections.abc import Callable

import pytest
from board import Board
from board.part import invalid_if
from test_install_watchdog_margin import (
    CANDIDATE_BUNDLE,
    GAP_S,
    LOW_TIMELEFT_S,
    READER,
    SECTOR_BYTES,
    SECTORS_WRITTEN,
    SOAK_LINE,
    STATS,
    Sample,
    _read,
    _uptime_at,
)

ARMS = "ABBAABBA"
# seconds from the case's start: no pair (two installs) begins after it, checked before installs 1, 3, 5 and 7
CUT_AFTER_S = 2000
# the first pair ends the run when its first install took longer than this
FIRST_SPAN_STOP_S = 285
# the first endpoint in arm A: PID 1 in state D within this many seconds of a journal start
NEAR_START_BEFORE_S = 15
NEAR_START_AFTER_S = 5
# a start counts as overlapping the write from this long before it to this long after it ended
OVERLAP_BEFORE_S = 5
OVERLAP_AFTER_S = 15
# the timer's next start reads as this while the soak unit runs
NEXT_UNSET = 2**64 - 1
NEXT_TRIES = 60
SILENT_BOARD_S = 600
UNDER_VOLTAGE = re.compile(r"\buv=1\b")
UP_AT_START_S = 400
A_LEAD_S = 225
SOAK_PERIOD_S = 300
MIN_FULL_WRITE_MIB = 1900
AFTER_START_S = 5
# arming 50 to 90 s, a write about 190 s, the end about 5 s, and margin; B begins within AFTER_START_S of a start
INSTALL_SPAN_S = 290
# systemctl prints the time as a span; the property raw is "t <microseconds>"
NEXT_START_CMD = (
    "busctl get-property org.freedesktop.systemd1 /org/freedesktop/systemd1/unit/kiosk_2dsoak_2etimer "
    "org.freedesktop.systemd1.Timer NextElapseUSecMonotonic"
)


def _wait_for_the_arm(board: Board, planned: str) -> float:
    """Wait until the install of arm `planned` should begin, from the timer's next start.

    Args:
        board: the board under test.
        planned: "A" or "B".

    Returns:
        The seconds waited.
    """
    next_start = NEXT_UNSET
    for _try in range(NEXT_TRIES):
        next_start = int(board.run(NEXT_START_CMD, check=True).text.split()[1])
        if next_start != NEXT_UNSET:
            break
        time.sleep(5)
    assert next_start != NEXT_UNSET, "the timer's next start was never set"
    ahead = next_start / 1e6 - board.uptime_s()
    wait = (ahead - A_LEAD_S) % SOAK_PERIOD_S if planned == "A" else ahead + AFTER_START_S
    time.sleep(max(0.0, wait))
    return max(0.0, wait)


def _boot_id_after(board: Board) -> str | None:
    """Read the boot id, reconnecting for up to `SILENT_BOARD_S` if the board does not answer.

    Args:
        board: the board under test.

    Returns:
        The boot id; None if the board did not answer in that time.
    """
    deadline = time.monotonic() + SILENT_BOARD_S
    while True:
        try:
            return board.boot_id()
        except Board.ERRORS:
            if time.monotonic() >= deadline:
                return None
            with contextlib.suppress(AssertionError, *Board.ERRORS):
                board.reconnect()
            time.sleep(5)


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


@pytest.mark.sends_update
def test_soak_start_arms(board: Board, record_property: Callable[[str, object], None]) -> None:
    """Install in turn, with the timer's start late in the write and with none, and record each reading.

    Args:
        board: the board under test.
        record_property: records each install's readings and the arm counts.
    """
    uptime = board.uptime_s()
    time.sleep(max(0.0, UP_AT_START_S - uptime))
    case_began = time.monotonic()
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
    endpoint = {"A": 0, "B": 0}
    dips = {"start": 0, "none": 0, "natural": 0, "void": 0}
    counted = {"start": 0, "none": 0, "natural": 0, "void": 0}
    stopped = "ended by an exception"
    first_span = 0.0
    try:
        for number, planned in enumerate(ARMS, start=1):
            if number % 2 and time.monotonic() - case_began >= CUT_AFTER_S:
                stopped = f"install {number}: past {CUT_AFTER_S} s from the case's start, no new pair begins"
                break
            if number == 3 and first_span > FIRST_SPAN_STOP_S:
                stopped = (
                    f"the first install took {first_span:.0f} s, over {FIRST_SPAN_STOP_S}: the first pair ends the run"
                )
                break
            waited = _wait_for_the_arm(board, planned)

            began = time.monotonic()
            watched = board.updates.install_watched(CANDIDATE_BUNDLE, lambda: None, SOAK_PERIOD_S)
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
            record_property(f"{key}.samples", len(window))
            record_property(f"{key}.span_s", round(finished - began, 1))
            record_property(f"{key}.over_span", finished - began > INSTALL_SPAN_S)
            if number == 1:
                first_span = finished - began
            if UNDER_VOLTAGE.search(watched.output):
                record_property(f"{key}.under_voltage", True)
                stopped = f"install {number}: under-voltage in its stats"
                break
            record_property(
                f"{key}.samples_all",
                "\n".join(
                    f"{s.uptime:.1f} {s.timeleft} {s.state} {s.pid1_state} {s.wchan} {s.reader_ticks}" for s in window
                ),
            )
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
            boot_now = _boot_id_after(board)
            if boot_now is None:
                stopped = f"install {number}: the board did not answer for {SILENT_BOARD_S} s"
                break
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
            write_from = write_to = None
            if window and watched.write_began is not None and watched.write_ended is not None:
                write_from = _uptime_at(window, watched.write_began)
                write_to = _uptime_at(window, watched.write_ended)
                record_property(f"{key}.write_uptime", f"{write_from:.1f}-{write_to:.1f}")
                in_write = [
                    t
                    for t in _journal_starts(board, boot)
                    if write_from - OVERLAP_BEFORE_S <= t <= write_to + OVERLAP_AFTER_S
                ]
            record_property(f"{key}.journal_starts_in_write", in_write)
            if write_from is not None and write_to > write_from:
                record_property(
                    f"{key}.start_share_of_write",
                    " ".join(f"{(t - write_from) / (write_to - write_from):.2f}" for t in in_write),
                )
            arm = ("start" if planned == "A" else "natural") if in_write else ("void" if planned == "A" else "none")
            record_property(f"{key}.arm_by_journal", arm)
            counted[arm] += 1
            in_write_samples = (
                [s for s in window if write_from <= s.uptime <= write_to] if write_from is not None else []
            )
            record_property(f"{key}.dip_in_write", any(s.timeleft < LOW_TIMELEFT_S for s in in_write_samples))
            dips[arm] += any(s.timeleft < LOW_TIMELEFT_S for s in in_write_samples)
            d_in_write = [s for s in in_write_samples if s.pid1_state == "D"]
            near = [
                s
                for s in d_in_write
                if any(-NEAR_START_BEFORE_S <= s.uptime - start <= NEAR_START_AFTER_S for start in in_write)
            ]
            record_property(f"{key}.pid1_in_D_in_write", len(d_in_write))
            record_property(f"{key}.pid1_in_D_near_a_start", len(near))
            reached = len(near) > 0 if planned == "A" else len(d_in_write) > 0
            record_property(f"{key}.first_endpoint", reached)
            endpoint[planned] += reached
        else:
            stopped = "all installs done"
    finally:
        reader.terminate()
        collector.join()
        record_property("stopped", stopped)
        record_property("installs_by_arm", counted)
        record_property("first_endpoint_installs_by_planned_arm", endpoint)
        record_property("installs_with_a_dip_by_arm", dips)
        record_property("samples", len(samples))

    with invalid_if("no timeleft could be read"):
        assert samples, "no sample"
