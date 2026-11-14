"""Target suite: the replayed page's motion stays within a bound of frame stalls."""

import subprocess
import time

import pytest
from labgrid.driver.exception import ExecutionError

from replay import CARDS4_LIVE

# the page's state under replay: four park cards, all live
FULL_CARDS = "4/4"
# setup error, not a failure, if the page never reaches full state
FULL_STATE_WAIT_SECONDS = 120
WARMUP_MS = 40_000
WINDOW_MS = 320_000
# the host sleeps this long inside the window, making no board read
WINDOW_SLEEP_SECONDS = 321
# how long past the window's end the page may take to report it
END_WAIT_SECONDS = 30
READ_PAUSE_SECONDS = 1
# a stall is a frame interval at or above this; the histogram's bin 3 starts here
CUTOFF_MS = 250
STALL_FROM_BIN = 3
HIST_BINS = 7
# the least share of report ticks that caught a marquee scrolling for the window to count
MOTION_FLOOR = 0.29

_COUNTERS = ("el", "frames", "isum", "ticks", "moving", "changes", "cost")
_SOC_TEMP_PATH = "/sys/class/thermal/thermal_zone0/temp"
_SOAK_LOG_PATH = "/data/kiosk-soak.log"


def _read(panel):
    """The panel's (uptime, sample), or (None, None) if the board did not answer."""
    try:
        return panel.read()
    except (ExecutionError, subprocess.TimeoutExpired):
        return None, None


def _full(panel, sample):
    return panel.on_panel(sample) and sample["cards"] == FULL_CARDS


def _counters(sample):
    """The probe's counters as ints, and its histogram as a list of ints.

    Raises:
        AssertionError: a counter is missing or malformed.
    """
    try:
        values = {key: int(sample[key]) for key in _COUNTERS}
        hist = [int(count) for count in sample["hist"].split(",")]
        assert len(hist) == HIST_BINS
    except (KeyError, ValueError, AssertionError):
        raise AssertionError(f"the probe's counters are missing from {sample!r}") from None
    return values, hist


@pytest.fixture
def full_state(panel):
    """Wait for the applied page on the board's own origin with every card live; return its read."""
    deadline = time.monotonic() + FULL_STATE_WAIT_SECONDS
    while True:
        uptime_s, sample = _read(panel)
        if _full(panel, sample):
            return uptime_s, sample
        assert time.monotonic() < deadline, (
            f"the page was not in full state within {FULL_STATE_WAIT_SECONDS} s; last: {sample!r}"
        )
        time.sleep(READ_PAUSE_SECONDS)


def _soc_temperature(board):
    stdout, _stderr, returncode = board.run(f"cat {_SOC_TEMP_PATH}")
    return int(stdout[0]) / 1000 if returncode == 0 and stdout else None


def _soak_samples_between(board, start_uptime, end_uptime):
    """How many kiosk-soak log lines fall inside the uptime span."""
    stdout, _stderr, _returncode = board.run(f"cat {_SOAK_LOG_PATH} 2>/dev/null; true")
    count = 0
    for line in stdout:
        fields = dict(token.split("=", 1) for token in line.split() if "=" in token)
        if "up" in fields and start_uptime <= float(fields["up"]) <= end_uptime:
            count += 1
    return count


@pytest.mark.parametrize("proxy", [str(CARDS4_LIVE / "flows.har")], indirect=True)
def test_motion_stutter(proxy, replay_window, panel, full_state, board, record_property):
    """TST009 motion stutter measured: count frame stalls over a 320 s window of the replayed page.

    The window opens `WARMUP_MS` of page time after the page first reads full state, and the
    host reads nothing from the board inside it. The window is invalid, never a pass or a
    failure, if the page reloaded or changed state, a read is not full state, too little motion
    was seen, or the replay killed a request.
    """
    record_property("requirement", "TST009")
    record_property("cutoff_ms", CUTOFF_MS)
    _, first = full_state
    first_el = int(first["el"])

    deadline = time.monotonic() + FULL_STATE_WAIT_SECONDS
    while True:
        start_uptime, start = _read(panel)
        if start is not None and int(start["el"]) >= first_el + WARMUP_MS:
            break
        assert time.monotonic() < deadline, f"the page stopped reporting; last: {start!r}"
        time.sleep(READ_PAUSE_SECONDS)
    start_temp = _soc_temperature(board)

    time.sleep(WINDOW_SLEEP_SECONDS)

    deadline = time.monotonic() + END_WAIT_SECONDS
    start_counters, start_hist = _counters(start)
    while True:
        end_uptime, end = _read(panel)
        if end is not None and int(end["el"]) >= start_counters["el"] + WINDOW_MS:
            break
        assert time.monotonic() < deadline, (
            f"the page stopped reporting within {END_WAIT_SECONDS} s; last: {end!r}"
        )
        time.sleep(READ_PAUSE_SECONDS)
    end_temp = _soc_temperature(board)
    killed = proxy.killed()
    soak_samples = _soak_samples_between(board, start_uptime, end_uptime)

    end_counters, end_hist = _counters(end)
    hist = [after - before for before, after in zip(start_hist, end_hist)]
    delta = {key: end_counters[key] - start_counters[key] for key in _COUNTERS}
    stalls = sum(hist[STALL_FROM_BIN:])
    moving_share = delta["moving"] / delta["ticks"] if delta["ticks"] else 0.0

    problems = []
    if start["load"] != end["load"]:
        problems.append("the page reloaded inside the window")
    if delta["changes"] != 0:
        problems.append("the page changed state inside the window")
    if not (_full(panel, start) and _full(panel, end)):
        problems.append("a read was not the applied page, on the board's own origin, cards live")
    if moving_share < MOTION_FLOOR:
        problems.append(f"too little motion seen in the window: {moving_share:.2f}")
    if killed:
        problems.append(f"the replay killed requests: {killed}")

    record_property("validity", "valid" if not problems else f"invalid: {'; '.join(problems)}")
    record_property("stalls", stalls)
    record_property("window_ms", delta["el"])
    record_property("frames", delta["frames"])
    record_property("fps", round(delta["frames"] * 1000 / delta["isum"], 2) if delta["isum"] else None)
    record_property("hist", ",".join(map(str, hist)))
    record_property("moving_share", round(moving_share, 3))
    record_property("probe_cost_ms", delta["cost"])
    record_property("load", end["load"])
    record_property("uptime_start", start_uptime)
    record_property("uptime_end", end_uptime)
    record_property("soc_temp_start", start_temp)
    record_property("soc_temp_end", end_temp)
    record_property("soak_samples_in_window", soak_samples)

    assert not problems, f"INVALID: {'; '.join(problems)}"
    # TST009's bound is not yet set: the window records its stall count and passes.
