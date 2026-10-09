"""Specifies cases/kiosk_units/verdict.py: shipped_units_verdict(units, glob_description),
show_properties(output), failed_unit_names(output), verdict(unit_properties, failed_units). One
parametrized test per function, one row per branch. Every `systemctl` shape here is a real one,
captured read-only on bench (`LoadState`/`LoadError`/`ActiveState`/`Result`, in the order systemd
itself printed them -- never assumed positional) or its documented `--failed --no-legend` column
layout; none is invented.
"""

import pytest

from oeqa.runtime.cases.kiosk_units.verdict import (
    failed_unit_names,
    shipped_units_verdict,
    show_properties,
    verdict,
)

# -- show_properties: real `systemctl show -p LoadState,LoadError,ActiveState,Result <unit>`
# shapes captured read-only on bench. systemd does not print properties in the order requested.
LOADED_CLEAN = "Result=success\nLoadState=loaded\nActiveState=active\nLoadError=\n"
NOT_FOUND = (
    "Result=success\nLoadState=not-found\nActiveState=inactive\n"
    'LoadError=org.freedesktop.systemd1.NoSuchUnit "Unit bogus.service not found."\n'
)


@pytest.mark.parametrize(
    ("name", "output", "want"),
    [
        (
            "a loaded unit, properties in systemd's own (non-alphabetical) order",
            LOADED_CLEAN,
            {"Result": "success", "LoadState": "loaded", "ActiveState": "active", "LoadError": ""},
        ),
        (
            "a never-loaded unit carries a populated LoadError",
            NOT_FOUND,
            {
                "Result": "success",
                "LoadState": "not-found",
                "ActiveState": "inactive",
                "LoadError": 'org.freedesktop.systemd1.NoSuchUnit "Unit bogus.service not found."',
            },
        ),
        ("blank lines are ignored", "\n  \n", {}),
    ],
)
def test_show_properties(name, output, want):
    assert show_properties(output) == want, name


# -- failed_unit_names: `systemctl list-units --failed --no-legend`'s own column layout, with its
# leading status marker (a UTF-8 bullet, captured as-is -- this parse never has to name it).
FAILED_LIST = "● kiosk-soak.timer loaded failed failed Soak timer\n"
EMPTY_FAILED_LIST = ""


@pytest.mark.parametrize(
    ("name", "output", "want"),
    [
        ("one failed unit, marker and all", FAILED_LIST, {"kiosk-soak.timer"}),
        ("no failed units at all is an empty set, never an error", EMPTY_FAILED_LIST, set()),
    ],
)
def test_failed_unit_names(name, output, want):
    assert failed_unit_names(output) == want, name


# -- verdict: unit_properties is {unit: show_properties(...)}; failed_units is
# failed_unit_names(...)'s own result.
LOADED = {"LoadState": "loaded", "LoadError": ""}
NOT_LOADED = {"LoadState": "not-found", "LoadError": 'NoSuchUnit "Unit x.service not found."'}
LOADED_WITH_ERROR = {"LoadState": "loaded", "LoadError": "some-error"}


@pytest.mark.parametrize(
    ("name", "unit_properties", "failed_units", "want_outcome", "want_reason_contains"),
    [
        ("no shipped units at all is ok -- nothing to report", {}, set(), "ok", ()),
        ("every unit loaded, none failed", {"a.service": LOADED, "b.service": LOADED}, set(), "ok", ()),
        (
            "a unit never loaded, named with its LoadError",
            {"a.service": NOT_LOADED},
            set(),
            "error",
            ("a.service", "not-found", "NoSuchUnit"),
        ),
        (
            "a loaded unit that still carries a LoadError",
            {"a.service": LOADED_WITH_ERROR},
            set(),
            "error",
            ("a.service", "some-error"),
        ),
        (
            "a cleanly loaded unit that systemctl list-units --failed still names",
            {"a.service": LOADED},
            {"a.service"},
            "error",
            ("a.service", "list-units --failed"),
        ),
        (
            "one good unit beside one bad one names only the bad one",
            {"a.service": LOADED, "b.service": NOT_LOADED},
            set(),
            "error",
            ("b.service",),
        ),
    ],
)
def test_verdict_outcome(name, unit_properties, failed_units, want_outcome, want_reason_contains):
    outcome, reason = verdict(unit_properties, failed_units)
    assert outcome == want_outcome, f"{name}: {reason!r}"
    for token in want_reason_contains:
        assert token in reason, f"{name}: {token!r} not in {reason!r}"


@pytest.mark.parametrize(
    ("name", "units", "want_outcome", "want_reason_contains"),
    [
        ("no units found is error, naming the caller's own glob description", (), "error", ("*.service",)),
        ("a non-empty list is ok", ("kiosk.service",), "ok", ()),
    ],
)
def test_shipped_units_verdict_outcome(name, units, want_outcome, want_reason_contains):
    outcome, reason = shipped_units_verdict(units, "*.service, *.timer")
    assert outcome == want_outcome, f"{name}: {reason!r}"
    for token in want_reason_contains:
        assert token in reason, f"{name}: {token!r} not in {reason!r}"
