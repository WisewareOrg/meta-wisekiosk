"""TST011-TST014: the performance window, judged by `verdicts.perf`."""

import time

from conftest import _run_text
from verdicts.applied import read_fields
from verdicts.perf import (
    cpu_idle,
    metrics,
    perf_sample,
    rss_total,
    thermal,
    validity,
    window_ended,
    window_reached,
)

WARMUP_MS = 15000
WINDOW_MS = 300000
THERMAL_EVERY_SECONDS = 30
_START_DEADLINE_SECONDS = 240
_END_DEADLINE_SECONDS = 30
_POLL_SECONDS = 2
_STAT = "head -n1 /proc/stat"
_THERMAL = "vcgencmd measure_temp && vcgencmd get_throttled"
_SOAK = 'L=$(mktemp) && KIOSK_SOAK_LOG="$L" kiosk-soak.sh && cat "$L"; rm -f "$L"'
_SOAK_TIMER = "kiosk-soak.timer"
_UNREAD = dict.fromkeys(
    ("fps", "p50", "stall", "maxstall", "ttp", "rss", "idle", "thermal", "cost"), "-"
)


def _wait(probe, done, deadline_s, what):
    """Poll `probe` until a sample satisfies `done`, or raise at the deadline.

    Args:
        probe: The `probe` fixture's own reader callable.
        done (Callable[[dict], bool]): Called with each parsed sample.
        deadline_s (float): Seconds to keep polling.
        what (str): Named in the raised message, for which wait timed out.

    Returns:
        dict: The first sample for which `done` returned True.

    Raises:
        RuntimeError: `deadline_s` elapsed with no such sample.
    """
    deadline = time.monotonic() + deadline_s
    while True:
        fields = read_fields(probe())
        sample = None if fields is None else perf_sample(fields)
        if sample is not None and done(sample):
            return sample
        if time.monotonic() >= deadline:
            raise RuntimeError(f"no {what} probe read within {deadline_s}s")
        time.sleep(_POLL_SECONDS)


def _measure(driver, probe, window_ms):
    """The window's two probe reads, its `/proc/stat` reads and its thermal readings.

    Stops `kiosk-soak.timer` for the window's own duration and restarts it once the window's
    reads are done, as the old pipeline's performance phase did -- the soak timer's own work is
    load the measurement is not meant to include.

    Args:
        driver: A labgrid SSHDriver.
        probe: The `probe` fixture's own reader callable.
        window_ms (int): The window's own length.

    Returns:
        tuple: `(start, end, stat_start, stat_end, readings)` -- the window's start and end
            probe samples, the `/proc/stat` reads bracketing the window, and every thermal
            reading taken during it.
    """
    start = _wait(
        probe, lambda s: window_reached(s, WARMUP_MS), _START_DEADLINE_SECONDS, "warmed-up"
    )
    _run_text(driver, f"systemctl stop {_SOAK_TIMER}")
    try:
        stat_start = _run_text(driver, _STAT)
        readings = [_run_text(driver, _THERMAL)]
        began = time.monotonic()
        for n in range(1, window_ms // 1000 // THERMAL_EVERY_SECONDS + 1):
            time.sleep(max(0, began + n * THERMAL_EVERY_SECONDS - time.monotonic()))
            readings.append(_run_text(driver, _THERMAL))
        end = _wait(
            probe, lambda s: window_ended(start, s, window_ms), _END_DEADLINE_SECONDS, "window-end"
        )
        stat_end = _run_text(driver, _STAT)
    finally:
        _run_text(driver, f"systemctl start {_SOAK_TIMER}")
    return start, end, stat_start, stat_end, readings


def test_perf_window(target, probe, replay_window, record_property):
    """TST011-TST014: frame rate, late frames, longest freeze, freeze rate and time to page,
    over a 300 s window starting 15 s after the page loads, under a replay set.

    Always recorded, under their own `record_property` key, whether or not the window turns
    out valid: `fps`, `p50`, `stall`, `maxstall`, `ttp`, `cost`, `rss`, `idle`, `thermal` -- `"-"`
    for any not reached before an earlier step raised.

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.
        probe: deploys `probe.js` and restarts the browser; yields a reader for the board's
            current window titles, raw.
        replay_window: switches the board into replay mode; yields the set's own `expected.json`.
        record_property: pytest's own fixture; attaches the recorded fields above.
    """
    driver = target.get_driver("SSHDriver")
    fields = dict(_UNREAD)
    try:
        start, end, stat_start, stat_end, readings = _measure(driver, probe, WINDOW_MS)
        rss = rss_total(_run_text(driver, _SOAK))
        window, reason = validity(start, end, replay_window)
        fields.update(rss=rss, idle=cpu_idle(stat_start, stat_end), thermal=thermal(readings))
        fields.update(metrics(start, end))
    finally:
        for key, value in fields.items():
            record_property(key, value)

    assert window != "void", f"void: {reason}"
