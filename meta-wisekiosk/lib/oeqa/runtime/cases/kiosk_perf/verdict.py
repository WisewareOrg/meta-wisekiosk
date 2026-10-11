"""The performance window's verdict: two probe reads differenced into the smoothness metrics,
the window's validity, and its context fields. Pure: every input is a plain Python value.
"""
import json
import re

_INT_FIELDS = ("t0", "el", "changes", "frames", "isum", "maxstall", "bt", "cost")
_HIST_BINS = 7
# hist bins: <50, 50-100, 100-250, 250-500, 500-1000, 1000-2000, >=2000 ms.
_STALL_FROM_BIN = 2
_EXPECTED_KEYS = ("cards", "faulted", "unreachable")
_TEMP = re.compile(r"^temp=([0-9.]+)'C$")
_THROTTLED = re.compile(r"^throttled=(0x[0-9a-fA-F]+)$")
_RSS_TOTAL = re.compile(r"(?:^|\s)rss_total=(\d+)(?:\s|$)")
THERMAL_LIMIT_C = 80.0
_CURRENT_BITS = 0xF
_STICKY_BITS = 0xF0000


def perf_sample(fields):
    """The typed sample from a payload's key=value dict; None if a field is missing or bad."""
    try:
        sample = {key: int(fields[key]) for key in _INT_FIELDS}
        hist = [int(n) for n in fields["hist"].split(",")]
        sample["ttp"] = None if fields["ttp"] == "-" else int(fields["ttp"])
        sample["state"], sample["cards"] = fields["state"], fields["cards"]
        for key in ("faulted", "unreachable"):
            sample[key] = int(fields[key])
    except (KeyError, ValueError):
        return None
    if len(hist) != _HIST_BINS:
        return None
    sample["hist"] = hist
    return sample


def expected_state(text):
    """expected.json's dict; ValueError unless exactly cards, faulted and unreachable."""
    state = json.loads(text)
    if not isinstance(state, dict) or sorted(state) != sorted(_EXPECTED_KEYS):
        raise ValueError(f"expected.json must carry exactly {', '.join(_EXPECTED_KEYS)}")
    return state


def window_reached(sample, warmup_ms):
    """Whether sample was written at least warmup_ms after the probe's t0."""
    return sample["el"] - sample["t0"] >= warmup_ms


def window_ended(start, sample, window_ms):
    """Whether sample was written at least window_ms after start."""
    return sample["el"] - start["el"] >= window_ms


def validity(start, end, expected):
    """("valid", "") if both reads are applied, equal expected, same changes; else ("void", why)."""
    for sample in (start, end):
        if sample["state"] != "applied":
            return "void", f"state={sample['state']} at el={sample['el']}"
        for key in _EXPECTED_KEYS:
            if sample[key] != expected[key]:
                return "void", f"{key}={sample[key]} at el={sample['el']}, expected {expected[key]}"
    if end["changes"] != start["changes"]:
        changed = end["changes"] - start["changes"]
        return "void", f"page state changed {changed} time(s) inside the window"
    return "valid", ""


def metrics(start, end):
    """fps, p50 (% under 50 ms), stall (>= 100 ms per minute), maxstall, ttp, cost."""
    frames = end["frames"] - start["frames"]
    isum = end["isum"] - start["isum"]
    if frames <= 0 or isum <= 0:
        raise ValueError(f"no frames between the reads (frames={frames} isum={isum})")
    hist = [b - a for a, b in zip(start["hist"], end["hist"])]
    return {
        "fps": round(frames * 1000 / isum, 2),
        "p50": round(100 * hist[0] / frames, 2),
        "stall": round(sum(hist[_STALL_FROM_BIN:]) * 60000 / isum, 2),
        "maxstall": end["maxstall"],
        "ttp": "-" if start["ttp"] is None else start["ttp"],
        "cost": end["cost"] - start["cost"],
    }


def _cpu_fields(stat_text):
    for line in stat_text.splitlines():
        parts = line.split()
        if parts and parts[0] == "cpu":
            return [int(n) for n in parts[1:]]
    raise ValueError("no aggregate cpu line in /proc/stat")


def cpu_idle(stat_start, stat_end):
    """% of CPU time idle between two /proc/stat reads' aggregate cpu lines."""
    start, end = _cpu_fields(stat_start), _cpu_fields(stat_end)
    total = sum(end) - sum(start)
    if total <= 0:
        raise ValueError("no CPU time passed between the /proc/stat reads")
    return round(100 * (end[3] - start[3]) / total, 2)


def rss_total(soak_line):
    """kiosk-soak.sh's rss_total (kB) from one of its sample lines."""
    m = _RSS_TOTAL.search(soak_line)
    if not m:
        raise ValueError("no rss_total in the kiosk-soak line")
    return int(m.group(1))


def _thermal_reading(output):
    lines = output.split("\n")
    temp = _TEMP.match(lines[0].strip())
    throttled = _THROTTLED.match(lines[1].strip()) if len(lines) > 1 else None
    if not temp or not throttled:
        raise ValueError(f"unreadable thermal sample: {output!r}")
    return float(temp.group(1)), int(throttled.group(1), 16)


def thermal(readings):
    """"ok" or "excluded:<cause>" over time-ordered vcgencmd temp+throttled outputs."""
    if not readings:
        raise ValueError("no thermal readings")
    parsed = [_thermal_reading(output) for output in readings]
    hottest = max(temp for temp, _ in parsed)
    if hottest > THERMAL_LIMIT_C:
        return f"excluded:temp={hottest}"
    current = 0
    for _, bits in parsed:
        current |= bits & _CURRENT_BITS
    if current:
        return f"excluded:current={current:#x}"
    newly = parsed[-1][1] & ~parsed[0][1] & _STICKY_BITS
    if newly:
        return f"excluded:sticky={newly:#x}"
    return "ok"
