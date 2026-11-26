"""Compile cache: the engine compile in this checkout read the store another checkout filled.

tools/engine-compile-reading.sh writes build/engine-compile-reading.txt; this test records it.
"""

from pathlib import Path

READING = Path(__file__).resolve().parents[2] / "build" / "engine-compile-reading.txt"
CACHEABLE_CALLS = 2552
TOLERANCE = 0.01


def test_engine_compile_reading(record_property) -> None:
    """Record every key of the reading and check what the arm and a finished compile must show.

    Args:
        record_property: pytest's fixture for a value kept in the run's report.
    """
    reading = dict(line.split("=", 1) for line in READING.read_text().splitlines() if "=" in line)
    for key, value in reading.items():
        record_property(key, value)
    if reading["state"] != "stopped" or "build_type" in reading:
        assert (
            reading["build_type"]
            == {"control": "MinSizeRel", "option": "MinSizeRel", "proof406": "Release"}[reading["arm"]]
        )
        assert reading["use_woff2"] == {"control": "ON", "option": "OFF", "proof406": "ON"}[reading["arm"]]
    if reading["state"] == "ended":
        calls = sum(int(reading[name]) for name in ("direct_cache_hit", "preprocessed_cache_hit", "cache_miss"))
        assert abs(calls - CACHEABLE_CALLS) <= CACHEABLE_CALLS * TOLERANCE
