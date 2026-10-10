"""Specifies cases/kiosk_units/verdict.py: show_properties(output), failed_unit_names(output),
verdict(unit_properties, failed_units). One parametrized test per function, one row per branch.
"""

import pytest

from oeqa.runtime.cases.kiosk_units.verdict import failed_unit_names, show_properties, verdict

# -- show_properties: real `systemctl show -p LoadState,LoadError <unit>` shapes captured
# read-only on bench. systemd does not print properties in the order requested.
LOADED_CLEAN = "LoadState=loaded\nLoadError=\n"
NOT_FOUND = 'LoadError=org.freedesktop.systemd1.NoSuchUnit "Unit bogus.service not found."\nLoadState=not-found\n'


@pytest.mark.parametrize(
    ("name", "output", "want"),
    [
        ("a loaded unit", LOADED_CLEAN, {"LoadState": "loaded", "LoadError": ""}),
        (
            "a never-loaded unit carries a populated LoadError, properties in reverse order",
            NOT_FOUND,
            {
                "LoadError": 'org.freedesktop.systemd1.NoSuchUnit "Unit bogus.service not found."',
                "LoadState": "not-found",
            },
        ),
        ("blank lines are ignored", "\n  \n", {}),
    ],
)
def test_show_properties(name, output, want):
    assert show_properties(output) == want, name


# -- failed_unit_names: `systemctl list-units --failed --no-legend`'s own column layout, with its
# leading status marker (a UTF-8 bullet) -- any unit type, not only one this layer ships.
FAILED_LIST = "● kiosk-soak.timer loaded failed failed Soak timer v1.2\n"
FAILED_LIST_NO_MARKER = "data.mount loaded failed failed /data\n"
FAILED_LIST_WITH_UNDOTTED_NOISE_LINE = (
    "resetting\n● kiosk-soak.timer loaded failed failed Soak timer v1.2\n"
)
EMPTY_FAILED_LIST = ""


@pytest.mark.parametrize(
    ("name", "output", "want"),
    [
        ("one failed unit, marker and a dotted description word", FAILED_LIST, ["kiosk-soak.timer"]),
        ("a non-service/timer unit type, no marker present", FAILED_LIST_NO_MARKER, ["data.mount"]),
        (
            "a line with no dotted token at all is skipped, not mistaken for a unit",
            FAILED_LIST_WITH_UNDOTTED_NOISE_LINE,
            ["kiosk-soak.timer"],
        ),
        ("no failed units at all is an empty list, never an error", EMPTY_FAILED_LIST, []),
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
    (
        "name", "unit_properties", "failed_units", "want_outcome",
        "want_reason_contains", "want_reason_excludes",
    ),
    [
        ("no shipped units at all is an error -- nothing was checked", {}, [], "error", ("no shipped units",), ()),
        ("every unit loaded, none failed", {"a.service": LOADED, "b.service": LOADED}, [], "ok", (), ()),
        (
            "a unit never loaded, named with its LoadError",
            {"a.service": NOT_LOADED},
            [],
            "error",
            ("a.service", "not-found", "NoSuchUnit"),
            (),
        ),
        (
            "a loaded unit that still carries a LoadError",
            {"a.service": LOADED_WITH_ERROR},
            [],
            "error",
            ("a.service", "some-error"),
            (),
        ),
        (
            "a failed unit of a type this layer does not even ship still fails the check",
            {"a.service": LOADED},
            ["data.mount"],
            "error",
            ("data.mount", "list-units --failed"),
            ("a.service",),
        ),
        (
            "one good unit beside one bad one names only the bad one",
            {"a.service": LOADED, "b.service": NOT_LOADED},
            [],
            "error",
            ("b.service",),
            ("a.service",),
        ),
    ],
)
def test_verdict_outcome(
    name, unit_properties, failed_units, want_outcome, want_reason_contains, want_reason_excludes,
):
    outcome, reason = verdict(unit_properties, failed_units)
    assert outcome == want_outcome, f"{name}: {reason!r}"
    for token in want_reason_contains:
        assert token in reason, f"{name}: {token!r} not in {reason!r}"
    for token in want_reason_excludes:
        assert token not in reason, f"{name}: {token!r} unexpectedly in {reason!r}"
