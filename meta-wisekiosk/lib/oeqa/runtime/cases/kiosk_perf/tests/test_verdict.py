"""Specifies cases/kiosk_perf/verdict.py against docs/requirements/tst/TST011-TST014.yml and
SRS010.yml. No device, no DOM -- every input is constructed."""

import pytest

from oeqa.runtime.cases.kiosk_perf.verdict import (
    cpu_idle,
    expected_state,
    metrics,
    perf_sample,
    rss_total,
    thermal,
    validity,
    window_ended,
    window_reached,
)

# ---------------------------------------------------------------------- perf_sample

FULL_FIELDS = {
    "t0": "1200", "el": "316200", "ttp": "16500", "changes": "3",
    "frames": "15100", "isum": "302345", "maxstall": "185", "bt": "42", "cost": "320",
    "hist": "12080,1510,305,103,21,11,2",
    "state": "applied", "cards": "4/4", "faulted": "0", "unreachable": "0",
}

FULL_SAMPLE = {
    "t0": 1200, "el": 316200, "changes": 3, "frames": 15100, "isum": 302345, "maxstall": 185,
    "bt": 42, "cost": 320, "ttp": 16500,
    "state": "applied", "cards": "4/4", "faulted": 0, "unreachable": 0,
    "hist": [12080, 1510, 305, 103, 21, 11, 2],
}


def test_perf_sample_parses_the_full_payload():
    assert perf_sample(FULL_FIELDS) == FULL_SAMPLE


def test_perf_sample_ttp_dash_is_not_yet_reached():
    fields = dict(FULL_FIELDS, ttp="-")
    assert perf_sample(fields)["ttp"] is None


@pytest.mark.parametrize(
    ("name", "missing_key"),  # one per distinct raise point: int field, hist, ttp, cards, faulted
    [(key, key) for key in ("frames", "hist", "ttp", "cards", "unreachable")],
)
def test_perf_sample_a_missing_field_is_not_a_sample(name, missing_key):
    fields = {k: v for k, v in FULL_FIELDS.items() if k != missing_key}
    assert perf_sample(fields) is None, name


def test_perf_sample_a_malformed_int_field_is_not_a_sample():
    assert perf_sample(dict(FULL_FIELDS, frames="not-a-number")) is None


def test_perf_sample_a_histogram_with_the_wrong_bin_count_is_not_a_sample():
    assert perf_sample(dict(FULL_FIELDS, hist="1,2,3,4,5,6")) is None


# ------------------------------------------------------------------ window_reached / window_ended

def test_window_reached_true_at_exactly_the_warmup():
    assert window_reached({"el": 15000, "t0": 0}, warmup_ms=15000) is True


def test_window_reached_false_just_before_the_warmup():
    assert window_reached({"el": 14999, "t0": 0}, warmup_ms=15000) is False


def test_window_ended_true_at_exactly_the_window():
    assert window_ended({"el": 15000}, {"el": 315000}, window_ms=300000) is True


def test_window_ended_false_just_before_the_window():
    assert window_ended({"el": 15000}, {"el": 314999}, window_ms=300000) is False


# ---------------------------------------------------------------------------- expected_state

CARDS4_LIVE_EXPECTED_JSON = '{"cards": "4/4", "faulted": 0, "unreachable": 0}'


def test_expected_state_parses_the_real_cards4_live_file():
    assert expected_state(CARDS4_LIVE_EXPECTED_JSON) == {
        "cards": "4/4", "faulted": 0, "unreachable": 0}


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("non-object", "[1, 2, 3]"),
        ("missing key", '{"cards": "4/4", "faulted": 0}'),
        ("extra key", '{"cards": "4/4", "faulted": 0, "unreachable": 0, "extra": 1}'),
    ],
)
def test_expected_state_rejects_invalid_input(name, text):
    with pytest.raises(ValueError):
        expected_state(text)


# ---------------------------------------------------------------------------- validity
# Phase A is always judged against a replay set (rulings-group2.md Q11): expected is never None.

EXPECTED = {"cards": "4/4", "faulted": 0, "unreachable": 0}


def _sample(el, changes=2, state="applied", cards="4/4", faulted=0, unreachable=0):
    return {
        "el": el, "changes": changes, "state": state, "cards": cards, "faulted": faulted,
        "unreachable": unreachable,
    }


def test_validity_valid_when_both_reads_match_and_nothing_changed_between_them():
    assert validity(_sample(15000), _sample(315000), EXPECTED) == ("valid", "")


def test_validity_voids_on_the_start_reads_non_applied_state():
    start = _sample(15000, state="loading")
    assert validity(start, _sample(315000), EXPECTED) == ("void", "state=loading at el=15000")


def test_validity_voids_on_the_end_reads_non_applied_state():
    end = _sample(315000, state="loading")
    assert validity(_sample(15000), end, EXPECTED) == ("void", "state=loading at el=315000")


def test_validity_voids_on_the_end_reads_cards_mismatch():
    end = _sample(315000, cards="4/1")
    assert validity(_sample(15000), end, EXPECTED) == (
        "void", "cards=4/1 at el=315000, expected 4/4")


def test_validity_voids_on_the_start_reads_faulted_mismatch():
    start = _sample(15000, faulted=1)
    assert validity(start, _sample(315000), EXPECTED) == (
        "void", "faulted=1 at el=15000, expected 0")


def test_validity_voids_on_an_unreachable_mismatch():
    end = _sample(315000, unreachable=1)
    assert validity(_sample(15000), end, EXPECTED) == (
        "void", "unreachable=1 at el=315000, expected 0")


def test_validity_voids_a_transient_fault_that_both_endpoints_missed():
    # Both endpoints read faulted=0 (matching expected); only changes caught the blip between.
    start, end = _sample(15000, changes=2, faulted=0), _sample(315000, changes=3, faulted=0)
    assert validity(start, end, EXPECTED) == (
        "void", "page state changed 1 time(s) inside the window")


def test_validity_checks_the_start_read_before_the_end_read():
    start = _sample(15000, cards="4/1")
    end = _sample(315000, faulted=1)
    assert validity(start, end, EXPECTED) == (
        "void", "cards=4/1 at el=15000, expected 4/4")


# ------------------------------------------------------------------------------ metrics
# hist's 7 bins: <50, 50-100, 100-250, 250-500, 500-1000, 1000-2000, >=2000 ms. p50 is bin 0 over
# frames; stall is bins 2.. per minute. maxstall and ttp come from the end/start read directly.

START_SAMPLE = {"frames": 100, "isum": 2000, "hist": [80, 10, 5, 3, 1, 1, 0], "maxstall": 50,
                "cost": 100, "ttp": 16500}
END_SAMPLE = {"frames": 15100, "isum": 302000, "hist": [12080, 1510, 305, 103, 21, 11, 2],
              "maxstall": 185, "cost": 320, "ttp": 99999}  # unused: ttp comes from the start read


def test_metrics_differences_the_cumulative_counters():
    assert metrics(START_SAMPLE, END_SAMPLE) == {
        "fps": 50.0, "p50": 80.0, "stall": 86.4, "maxstall": 185, "ttp": 16500, "cost": 220,
    }


def test_metrics_ttp_is_the_literal_dash_when_the_start_read_has_not_reached_it():
    start = dict(START_SAMPLE, ttp=None)
    assert metrics(start, END_SAMPLE)["ttp"] == "-"


def test_metrics_raises_when_no_frame_landed_between_the_reads():
    same = dict(START_SAMPLE)
    with pytest.raises(ValueError):
        metrics(same, same)


def test_metrics_raises_when_isum_did_not_advance():
    end = dict(END_SAMPLE, isum=START_SAMPLE["isum"])
    with pytest.raises(ValueError):
        metrics(START_SAMPLE, end)


# -------------------------------------------------------------------------------- cpu_idle
# /proc/stat's aggregate "cpu" line: idle is the 4th column.

STAT_START = "cpu  1000 0 500 8000 200 0 50 0 0 0\ncpu0 500 0 250 4000 100 0 25 0 0 0\n"
STAT_END = "cpu  1100 0 550 8900 210 0 55 0 0 0\ncpu0 550 0 275 4450 105 0 27 0 0 0\n"


def test_cpu_idle_percent_from_the_aggregate_line():
    assert cpu_idle(STAT_START, STAT_END) == 84.51


def test_cpu_idle_raises_with_no_aggregate_cpu_line():
    with pytest.raises(ValueError):
        cpu_idle("cpu0 1 2 3 4\n", STAT_END)


def test_cpu_idle_raises_when_no_cpu_time_passed():
    with pytest.raises(ValueError):
        cpu_idle(STAT_START, STAT_START)


# -------------------------------------------------------------------------------- rss_total

SOAK_LINE = "pid=1234 nproc=3 rss_main=45000 rss_total=98765\n"


def test_rss_total_from_a_real_shaped_soak_line():
    assert rss_total(SOAK_LINE) == 98765


def test_rss_total_raises_with_no_rss_total_field():
    with pytest.raises(ValueError):
        rss_total("pid=none nproc=0 rss_main=0\n")


def test_rss_total_does_not_match_a_field_name_ending_in_the_same_text():
    with pytest.raises(ValueError):
        rss_total("pid=1234 xrss_total=5\n")


# ---------------------------------------------------------------------------------- thermal
# vcgencmd's two-line output: "temp=45.2'C" then "throttled=0x50000". Bits 0-3 are CURRENT;
# bits 16-19 are STICKY (occurred since boot, never clear on their own).

def _reading(temp, throttled):
    return f"temp={temp}'C\nthrottled={throttled}"


def test_thermal_ok_when_nothing_crosses_the_limit():
    readings = [_reading("45.2", "0x0"), _reading("46.0", "0x0")]
    assert thermal(readings) == "ok"


def test_thermal_excluded_when_a_reading_exceeds_the_limit():
    readings = [_reading("45.2", "0x0"), _reading("81.5", "0x0")]
    assert thermal(readings) == "excluded:temp=81.5"


def test_thermal_excluded_on_a_current_bit():
    readings = [_reading("45.0", "0x1"), _reading("46.0", "0x0")]
    assert thermal(readings) == "excluded:current=0x1"


def test_thermal_excluded_on_a_sticky_bit_newly_set_during_the_window():
    readings = [_reading("45.0", "0x0"), _reading("46.0", "0x10000")]
    assert thermal(readings) == "excluded:sticky=0x10000"


def test_thermal_a_sticky_bit_already_set_at_the_start_is_not_newly_set():
    # Catches a missing "~start" term the "newly set" case above alone would not.
    readings = [_reading("45.0", "0x10000"), _reading("46.0", "0x10000")]
    assert thermal(readings) == "ok"


def test_thermal_temperature_takes_priority_over_a_current_bit():
    readings = [_reading("85.0", "0x1")]
    assert thermal(readings) == "excluded:temp=85.0"


@pytest.mark.parametrize(
    ("name", "readings"),
    [
        ("no readings", []),
        ("an unreadable reading", ["not a temp line\nthrottled=0x0"]),
        ("a reading with no second line", ["temp=45.2'C"]),
    ],
)
def test_thermal_raises(name, readings):
    with pytest.raises(ValueError):
        thermal(readings)
