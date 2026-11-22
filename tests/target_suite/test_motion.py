"""Target suite: the replayed page's motion stays within a bound of frame stalls."""

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from board import Board
from panel import Panel
from replay import CARDS4_LIVE

if TYPE_CHECKING:
    from wisebench.proxy import Proxy

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
# TST009's bound: the most stalls a window may hold
STALL_BOUND = 24
# the longest the start read may take to reach the warm-up
WARMUP_READ_WAIT_SECONDS = 120
# the least share of report ticks that caught a marquee scrolling for the window to count
MOTION_FLOOR = 0.29

_COUNTERS = ("el", "frames", "isum", "ticks", "moving", "changes", "cost")
_SOC_TEMP_PATH = "/sys/class/thermal/thermal_zone0/temp"
_SOAK_LOG_PATH = "/data/kiosk-soak.log"
# more of kiosk-soak's samples than any window spans
_SOAK_TAIL_LINES = 20


def _counters(sample: dict[str, str]) -> tuple[dict[str, int], list[int]]:
    """The probe's counters as ints, and its histogram as a list of ints.

    Args:
        sample: the probe's sample.

    Returns:
        The counters named in `_COUNTERS`, and the histogram's bins.

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


def _soc_temperature(board: Board) -> float | None:
    """The SoC temperature in degrees Celsius.

    Args:
        board: the board under test.

    Returns:
        The temperature, or None if the read returned nonzero or nothing.
    """
    stdout, _stderr, returncode = board.run(f"cat {_SOC_TEMP_PATH}")
    return int(stdout[0]) / 1000 if returncode == 0 and stdout else None


def _soak_samples_between(board: Board, start_uptime: float, end_uptime: float) -> int:
    """How many of kiosk-soak's last log lines, from this boot, fall inside the uptime span.

    Args:
        board: the board under test.
        start_uptime: the span's start, in board uptime seconds.
        end_uptime: the span's end, in board uptime seconds.

    Returns:
        The count of log lines from this boot whose `up` field is inside the span.
    """
    stdout, _stderr, _returncode = board.run(
        f"cut -c1-8 /proc/sys/kernel/random/boot_id; tail -n {_SOAK_TAIL_LINES} {_SOAK_LOG_PATH} 2>/dev/null; true"
    )
    boot = stdout[0]
    count = 0
    for line in stdout[1:]:
        fields = dict(token.split("=", 1) for token in line.split() if "=" in token)
        if fields.get("boot") == boot and start_uptime <= float(fields["up"]) <= end_uptime:
            count += 1
    return count


@pytest.mark.parametrize("proxy", [str(CARDS4_LIVE / "flows.har")], indirect=True)
def test_motion_stutter(
    proxy: "Proxy",
    replay_window: float,
    panel: Panel,
    board: Board,
    record_property: Callable[[str, object], None],
) -> None:
    """TST009 motion stutter measured: at most `STALL_BOUND` frame stalls in the window.

    The window opens `WARMUP_MS` of page time after the page first reads full state, and the
    host reads nothing from the board between the start read's temperature and the end read.
    The window is invalid, never a pass or a failure, if the page reloaded or changed state, a read is not
    full state, too little motion was seen, or the replay killed a request.

    Args:
        proxy: the replaying proxy, asked how many requests it killed.
        replay_window: puts the backend behind the proxy and the browser on the replayed page.
        panel: the probe in the browser, read for the counters.
        board: the board under test, whose temperature and soak log are read.
        record_property: records the requirement and what the window measured.

    Raises:
        AssertionError: the page stopped reporting, the window is invalid, or it held more than
            `STALL_BOUND` stalls.
        Failed: the page reloaded inside the window (INVALID).
    """
    record_property("requirement", "TST009")
    record_property("cutoff_ms", CUTOFF_MS)
    record_property("bound", STALL_BOUND)
    _, first = panel.wait_on_panel(full=True)
    first_el = int(first["el"])

    waited_s, start_read = panel.until(
        lambda read: read[1] is not None and int(read[1]["el"]) >= first_el + WARMUP_MS,
        WARMUP_READ_WAIT_SECONDS,
        every=READ_PAUSE_SECONDS,
    )
    assert waited_s is not None, f"the page stopped reporting; last: {start_read!r}"
    start_uptime, start, _ = start_read
    start_temp = _soc_temperature(board)
    start_counters, start_hist = _counters(start)

    time.sleep(WINDOW_SLEEP_SECONDS)

    waited_s, end_read = panel.until(
        lambda read: (
            read[1] is not None
            and (read[1]["load"] != start["load"] or int(read[1]["el"]) >= start_counters["el"] + WINDOW_MS)
        ),
        END_WAIT_SECONDS,
        every=READ_PAUSE_SECONDS,
    )
    assert waited_s is not None, f"the page stopped reporting within {END_WAIT_SECONDS} s; last: {end_read!r}"
    end_uptime, end, _ = end_read
    if end["load"] != start["load"]:
        reloaded = "the page reloaded inside the window"
        record_property("validity", f"invalid: {reloaded}")
        pytest.fail(f"INVALID: {reloaded}")
    end_temp = _soc_temperature(board)
    killed = proxy.killed()
    soak_samples = _soak_samples_between(board, start_uptime, end_uptime)

    end_counters, end_hist = _counters(end)
    hist = [after - before for before, after in zip(start_hist, end_hist)]
    delta = {key: end_counters[key] - start_counters[key] for key in _COUNTERS}
    stalls = sum(hist[STALL_FROM_BIN:])
    moving_share = delta["moving"] / delta["ticks"] if delta["ticks"] else 0.0

    problems = []
    if delta["changes"] != 0:
        problems.append("the page changed state inside the window")
    if not (panel.is_full(start) and panel.is_full(end)):
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
    assert stalls <= STALL_BOUND, (
        f"{stalls} frame stalls of {CUTOFF_MS} ms or more in {WINDOW_MS // 1000} s; bound {STALL_BOUND}"
    )
