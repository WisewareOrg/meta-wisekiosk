"""Diagnostics: does a kiosk-soak start inside a slot write starve the hardware watchdog?

Installs the candidate's own deployed bundle into the other slot while a separate ssh session reads
the watchdog's `timeleft` and state, PID 1's state letter and wait channel, the uptime and its own
CPU ticks, once a second, with builtins only (no process is started for a read). Once RAUC copies
the image, and again every `EVERY_S` seconds while it does, the case starts `kiosk-soak.service`
itself: the same PID 1 path as the timer's run, several times in one write. The result says
"started by the test", and is not a measure of the natural 5 minute cadence; the timer is left
running and its starts are recorded too. A start that fails or times out is a reading, recorded
with its time, and delays the watch by up to its timeout.

It records every sample and gives no verdict on them. It fails only when the reading is invalid: the
board had been up under `MIN_UPTIME_S`, no `timeleft` could be read, the install wrote under
`MIN_WRITTEN_MIB`, or the journal shows no soak start inside the write. The readings are recorded
before that is judged. A gap over `GAP_S` between samples, from the install's start to the first
sample, or from the last sample to the install's end, is recorded as a finding with its time.

Outside the regression suite: run by hand through the bench driver after the suite's own tests, with
this file added by path.
"""

import collections
import contextlib
import pathlib
import re
import subprocess
import threading
import time
from collections.abc import Callable
from typing import NamedTuple

import pytest
from board import Board
from board.part import invalid_if

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CANDIDATE_BUNDLE = (
    _REPO_ROOT
    / "build"
    / "tmp-raspberrypi0-wifi"
    / "deploy"
    / "images"
    / "raspberrypi0-wifi"
    / "update-bundle-raspberrypi0-wifi.raucb"
)
MIN_UPTIME_S = 1500
EVERY_S = 20
LOW_TIMELEFT_S = 7
GAP_S = 2.0
MIN_WRITTEN_MIB = 50
# one sh, builtins only: `read -t 1` on the ssh's stdin, which stays open, is the 1 s wait
READER = (
    "while :; do read u _ < /proc/uptime; read t < /sys/class/watchdog/watchdog0/timeleft; "
    "read s < /sys/class/watchdog/watchdog0/state; read _ _ c _ < /proc/1/stat; read w < /proc/1/wchan; "
    "read _ _ _ _ _ _ _ _ _ _ _ _ _ x y _ < /proc/$$/stat; "
    'echo "$u $t $s $c ${w:-none} $((x + y))"; read -t 1 _; done'
)
STATS = re.compile(r"\[stats\] .*mmc=((?:\d+ ?)+)")
SOAK_LINE = re.compile(r"^\[\s*(?P<up>\d+\.\d+)\]\s.*\bStarting\b")
SECTORS_WRITTEN = 6
SECTOR_BYTES = 512


class Sample(NamedTuple):
    """One reading of the watchdog and PID 1.

    Attributes:
        host: the host's `time.monotonic()` when the line arrived.
        uptime: the board's uptime.
        timeleft: seconds the watchdog had left.
        state: the watchdog's state.
        pid1_state: PID 1's state letter.
        wchan: PID 1's wait channel.
        reader_ticks: the reader's own CPU, in clock ticks since it began.
    """

    host: float
    uptime: float
    timeleft: int
    state: str
    pid1_state: str
    wchan: str
    reader_ticks: int


def _read(reader: subprocess.Popen, samples: list[Sample]) -> None:
    """Collect the reader's lines until it ends, skipping any that is not a whole reading.

    Args:
        reader: the ssh running `READER`.
        samples: where the readings go.
    """
    for line in reader.stdout:
        fields = line.split()
        with contextlib.suppress(ValueError, IndexError, TypeError):
            samples.append(Sample(time.monotonic(), float(fields[0]), int(fields[1]), *fields[2:5], int(fields[5])))


def _uptime_at(samples: list[Sample], host: float) -> float:
    """The board's uptime at a host instant, from the nearest sample.

    Args:
        samples: the readings; not empty.
        host: a host `time.monotonic()` instant.

    Returns:
        The nearest sample's uptime, moved by the difference in host time.
    """
    nearest = min(samples, key=lambda s: abs(s.host - host))
    return nearest.uptime + (host - nearest.host)


def _soak_journal(board: Board, boot_at_start: str, record_property: Callable[[str, object], None]) -> list[str]:
    """Read the soak unit's journal of the boot the install began in, reconnecting if the board reset.

    Args:
        board: the board under test.
        boot_at_start: the boot id the install began in.
        record_property: records the journal, whether the boot changed, or why it could not be read.

    Returns:
        The journal's lines; empty if they could not be read.
    """
    try:
        try:
            boot_now = board.boot_id()
        except Board.ERRORS:
            board.reconnect()
            boot_now = board.boot_id()
        record_property("boot_changed", boot_now != boot_at_start)
        lines = board.run(
            f"journalctl -b {boot_at_start.replace('-', '')} -u kiosk-soak.service -o short-monotonic --no-pager",
            check=True,
        ).stdout
    except (AssertionError, *Board.ERRORS) as error:
        record_property("journal_not_read", f"{type(error).__name__}: {error}")
        return []
    record_property("soak_journal", "\n".join(lines))
    return lines


@pytest.mark.sends_update
def test_install_watchdog_margin(board: Board, record_property: Callable[[str, object], None]) -> None:
    """Record how low `timeleft` goes while soak starts fall inside a slot write.

    Args:
        board: the board under test.
        record_property: records the readings.
    """
    uptime = board.uptime_s()
    boot_at_start = board.boot_id()
    with invalid_if(f"the board had been up under {MIN_UPTIME_S} s"):
        assert uptime >= MIN_UPTIME_S, f"up {uptime:.0f} s"

    samples: list[Sample] = []
    test_starts: list[tuple[float, str]] = []
    reader = subprocess.Popen(
        [*board.fresh_ssh_argv("ServerAliveInterval=2"), READER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    collector = threading.Thread(target=_read, args=(reader, samples))
    collector.start()

    def start_soak() -> None:
        """Start the soak unit and note when, and how it failed if it did."""
        try:
            board.run("systemctl start --no-block kiosk-soak.service", check=True)
            test_starts.append((time.monotonic(), "ok"))
        except (AssertionError, *Board.ERRORS) as error:
            test_starts.append((time.monotonic(), f"failed: {type(error).__name__}"))

    began = time.monotonic()
    watched = None
    write_from = write_to = None
    mib = 0.0
    try:
        watched = board.updates.install_watched(CANDIDATE_BUNDLE, start_soak, EVERY_S)
    finally:
        finished = time.monotonic()
        reader.terminate()
        collector.join()
        record_property("uptime_at_start", uptime)
        record_property("samples", len(samples))
        record_property("test_starts", "; ".join(f"{t - began:.1f}s {how}" for t, how in test_starts))
        if watched is not None:
            written = [
                int(m.group(1).split()[SECTORS_WRITTEN]) for m in map(STATS.search, watched.output.splitlines()) if m
            ]
            mib = (max(written) - min(written)) * SECTOR_BYTES / 2**20 if written else 0.0
            record_property("install_rc", watched.returncode)
            record_property("install_seconds", watched.seconds)
            record_property("written_mib", mib)
        if samples:
            record_property(
                "all_samples",
                "\n".join(
                    f"{s.host - began:.1f} {s.uptime:.1f} {s.timeleft} {s.state} {s.pid1_state} {s.wchan} "
                    f"{s.reader_ticks}"
                    for s in samples
                ),
            )
            lowest = min(samples, key=lambda s: s.timeleft)
            low = [s for s in samples if s.timeleft < LOW_TIMELEFT_S]
            stamps = [(began, None), *((s.host, s.uptime) for s in samples), (finished, None)]
            gaps = [
                f"after {'the install start' if first_up is None else f'uptime {first_up:.0f}'}: {second - first:.1f} s"
                for (first, first_up), (second, _up) in zip(stamps, stamps[1:], strict=False)
                if second - first > GAP_S
            ]
            record_property("timeleft_min", lowest.timeleft)
            record_property("timeleft_min_uptime", lowest.uptime)
            record_property("samples_below_7s", len(low))
            record_property("pid1_states", dict(collections.Counter(s.pid1_state for s in samples)))
            record_property("pid1_wchan", dict(collections.Counter(s.wchan for s in samples)))
            record_property("gaps_over_2s", "; ".join(gaps))
            if watched is not None and watched.write_began is not None and watched.write_ended is not None:
                write_from = _uptime_at(samples, watched.write_began)
                write_to = _uptime_at(samples, watched.write_ended)
                record_property("write_uptime_from", write_from)
                record_property("write_uptime_to", write_to)
                record_property("write_seconds", watched.write_ended - watched.write_began)

    journal = _soak_journal(board, boot_at_start, record_property)

    with invalid_if("no timeleft could be read"):
        assert samples, "no sample"
    with invalid_if(f"the install wrote under {MIN_WRITTEN_MIB} MiB"):
        assert mib >= MIN_WRITTEN_MIB, f"{mib:.1f} MiB"
    starts = [float(m["up"]) for line in journal if (m := SOAK_LINE.match(line))]
    with invalid_if("the journal shows no soak start inside the slot write"):
        assert write_from is not None and any(write_from <= start <= write_to for start in starts), (
            f"starts {starts}, write {write_from} to {write_to}"
        )
