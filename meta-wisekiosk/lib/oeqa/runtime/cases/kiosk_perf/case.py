import os
import time
from pathlib import Path

from framework import record
from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS, POLL_SECONDS
from kiosk_applied.verdict import read_fields

from . import verdict

WARMUP_MS = 15000
WINDOW_MS = 300000
THERMAL_EVERY_SECONDS = 30
START_DEADLINE_SECONDS = 240
END_DEADLINE_SECONDS = 30

_SETS = Path(__file__).resolve().parents[6] / "tools" / "replay" / "sets"
_STAT = "head -n1 /proc/stat"
_THERMAL = "vcgencmd measure_temp && vcgencmd get_throttled"
_SOAK = 'L=$(mktemp) && KIOSK_SOAK_LOG="$L" kiosk-soak.sh && cat "$L"; rm -f "$L"'
_UNREAD = dict.fromkeys(
    ("fps", "p50", "stall", "maxstall", "ttp", "rss", "idle", "thermal", "cost"), "-")


def run(case, command):
    """case.target.run's output, raising on a non-zero status."""
    status, output = case.target.run(command, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
    if status != 0:
        raise RuntimeError(f"transport: {command.split()[0]} exited {status}")
    return output


def _wait(case, done, deadline_s, what):
    deadline = time.monotonic() + deadline_s
    while True:
        fields = read_fields(case.titles())
        sample = None if fields is None else verdict.perf_sample(fields)
        if sample is not None and done(sample):
            return sample
        if time.monotonic() >= deadline:
            raise RuntimeError(f"transport: no {what} probe read within {deadline_s}s")
        time.sleep(POLL_SECONDS)


def measure(case, window_ms):
    """The window's two probe reads, its /proc/stat reads and its thermal readings, every
    THERMAL_EVERY_SECONDS from start to end."""
    start = _wait(case, lambda s: verdict.window_reached(s, WARMUP_MS),
                  START_DEADLINE_SECONDS, "warmed-up")
    stat_start = run(case, _STAT)
    readings = [run(case, _THERMAL)]
    began = time.monotonic()
    for n in range(1, window_ms // 1000 // THERMAL_EVERY_SECONDS + 1):
        time.sleep(max(0, began + n * THERMAL_EVERY_SECONDS - time.monotonic()))
        readings.append(run(case, _THERMAL))
    end = _wait(case, lambda s: verdict.window_ended(start, s, window_ms),
                END_DEADLINE_SECONDS, "window-end")
    return start, end, stat_start, run(case, _STAT), readings


class KioskPerfTest(WiseKioskCase):

    def _record(self, **fields):
        self.tc.extraresults[record.RECORD_KEY]["perf"] = record.perf_line(**{**_UNREAD, **fields})

    def test_perf_window(self):
        self._record()
        perf_set = os.environ.get("PIPELINE_PERF_SET")
        if not perf_set:
            raise RuntimeError("PIPELINE_PERF_SET names no replay set for the window")
        expected = verdict.expected_state((_SETS / perf_set / "expected.json").read_text())

        start, end, stat_start, stat_end, readings = measure(self, WINDOW_MS)
        rss = verdict.rss_total(run(self, _SOAK))
        window, reason = verdict.validity(start, end, expected)
        self._record(rss=rss, idle=verdict.cpu_idle(stat_start, stat_end),
                     thermal=verdict.thermal(readings), **verdict.metrics(start, end))
        if window == "void":
            self.fail(f"void: {reason}")
