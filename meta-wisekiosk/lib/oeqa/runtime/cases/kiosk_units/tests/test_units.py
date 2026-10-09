"""Specifies cases/kiosk_units/verdict.py: verdict(status, output, active_units) and
not_found_names(output). One parametrized test, one row per branch.
"""

import pytest

from oeqa.runtime.cases.kiosk_units.verdict import not_found_names, verdict

# The real line from the pipeline's own kiosk.service/kiosk-provision.service failures.
KIOSK_DATA_MOUNT_NOT_FOUND = "kiosk.service: Failed to create kiosk.service/start: Unit data.mount not found."
PROVISION_DATA_MOUNT_NOT_FOUND = "kiosk-provision.service: Failed to create kiosk-provision.service/start: Unit data.mount not found."

EXECSTART_MISSING = "kiosk.service: Service has no ExecStart=, ExecStop=, or SuccessAction=. Refusing."

# The real shapes a missing systemd-analyze package or an unreachable board produce.
COMMAND_NOT_FOUND = "bash: line 1: systemd-analyze: command not found"
CONNECTION_REFUSED = "ssh: connect to host 192.0.2.1 port 22: Connection refused"


@pytest.mark.parametrize(
    ("name", "status", "output", "active_units", "want_outcome", "want_reason_contains", "want_reason_excludes"),
    [
        ("clean verify, no output at all", 0, "", {}, "ok", (), ()),
        ("output present but only blank lines", 0, "\n  \n", {}, "ok", (), ()),
        (
            "one not-found line excused by an active board answer",
            1,
            KIOSK_DATA_MOUNT_NOT_FOUND,
            {"data.mount": "active"},
            "ok",
            (),
            (),
        ),
        (
            "one not-found line not excused (any non-active answer, including never queried)",
            1,
            KIOSK_DATA_MOUNT_NOT_FOUND,
            {},
            "error",
            ("data.mount",),
            (),
        ),
        (
            "a genuine defect with no not-found shape survives regardless of active_units",
            1,
            EXECSTART_MISSING,
            {"data.mount": "active"},
            "error",
            ("Refusing",),
            (),
        ),
        (
            "several excused not-found lines together, still ok",
            1,
            KIOSK_DATA_MOUNT_NOT_FOUND + "\n" + PROVISION_DATA_MOUNT_NOT_FOUND,
            {"data.mount": "active"},
            "ok",
            (),
            (),
        ),
        (
            "an excused line beside a genuine one names only the genuine one",
            1,
            KIOSK_DATA_MOUNT_NOT_FOUND + "\n" + EXECSTART_MISSING,
            {"data.mount": "active"},
            "error",
            ("Refusing",),
            ("data.mount",),
        ),
        ("the package is missing, named verbatim", 127, COMMAND_NOT_FOUND, {}, "error", ("command not found",), ()),
        ("the board is unreachable, named verbatim", 255, CONNECTION_REFUSED, {}, "error", ("Connection refused",), ()),
        ("non-zero status with no diagnostic at all, status named", 137, "", {}, "error", ("137",), ()),
    ],
)
def test_verdict_outcome(name, status, output, active_units, want_outcome, want_reason_contains, want_reason_excludes):
    outcome, reason = verdict(status, output, active_units)
    assert outcome == want_outcome, f"{name}: {reason!r}"
    for token in want_reason_contains:
        assert token in reason, f"{name}: {token!r} not in {reason!r}"
    for token in want_reason_excludes:
        assert token not in reason, f"{name}: {token!r} unexpectedly in {reason!r}"


def test_not_found_names_extracts_every_name():
    names = not_found_names(KIOSK_DATA_MOUNT_NOT_FOUND + "\n" + EXECSTART_MISSING)
    assert names == {"data.mount"}
