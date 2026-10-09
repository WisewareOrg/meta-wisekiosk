"""Specifies cases/kiosk_image/verdict.py's two functions: execstart_verdict,
path_presence_verdict. One parametrized test per function, one row per branch.
"""

import pytest

from oeqa.runtime.cases.kiosk_image.verdict import (
    REQUIRED_DISPLAY_FLAGS,
    execstart_verdict,
    path_presence_verdict,
)

# ================================================================== execstart_verdict
KIOSK_SERVICE_UNIT = """[Unit]
Description=Kiosk browser: surf on bare Xorg, no display manager, no window manager
After=network-online.target data.mount
Wants=network-online.target
Requires=data.mount

[Service]
Type=simple
Environment=KIOSK_URL=http://localhost:8080
EnvironmentFile=-/data/config/kiosk.conf
ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1 -s 0 -dpms -nocursor
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

UNIT_MISSING_FLAGS = KIOSK_SERVICE_UNIT.replace(
    "ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1 -s 0 -dpms -nocursor",
    "ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1",
)

# A token that is a superstring of "-s 0" ("-s 05"), not a match under a token-boundary
# comparison -- the substring match this replaced would have wrongly passed it.
UNIT_FLAG_SUPERSTRING = KIOSK_SERVICE_UNIT.replace(
    "ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1 -s 0 -dpms -nocursor",
    "ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1 -s 05 -dpms -nocursor",
)

DROPIN_RESETS_AND_DROPS_FLAGS = """[Service]
ExecStart=
ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1
"""

DROPIN_RESETS_AND_RESTORES_FLAGS = """[Service]
ExecStart=
ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1 -s 0 -dpms -nocursor
"""

DROPIN_RESETS_ONLY = """[Service]
ExecStart=
"""

DROPIN_EXECSTART_OUTSIDE_SERVICE = """[Unit]
ExecStart=/usr/bin/not-a-real-directive-here
"""


@pytest.mark.parametrize(
    ("name", "unit_text", "dropin_texts", "want_outcome", "want_reason_contains"),
    [
        ("unit alone, every flag present", KIOSK_SERVICE_UNIT, [], "ok", ()),
        ("unit alone, flags missing, named", UNIT_MISSING_FLAGS, [], "error", REQUIRED_DISPLAY_FLAGS),
        ("a superstring of a flag token is not a match", UNIT_FLAG_SUPERSTRING, [], "error", ("-s 0",)),
        (
            "one drop-in resets ExecStart= and drops the flags",
            KIOSK_SERVICE_UNIT,
            [DROPIN_RESETS_AND_DROPS_FLAGS],
            "error",
            (),
        ),
        (
            "drop-in resets with nothing after -- no ExecStart= survives, named",
            KIOSK_SERVICE_UNIT,
            [DROPIN_RESETS_ONLY],
            "error",
            ("no", "ExecStart"),
        ),
        (
            "two drop-ins in order: first drops the flags, second restores them",
            KIOSK_SERVICE_UNIT,
            [DROPIN_RESETS_AND_DROPS_FLAGS, DROPIN_RESETS_AND_RESTORES_FLAGS],
            "ok",
            (),
        ),
        (
            "an ExecStart=-looking line outside [Service] is ignored",
            KIOSK_SERVICE_UNIT,
            [DROPIN_EXECSTART_OUTSIDE_SERVICE],
            "ok",
            (),
        ),
    ],
)
def test_execstart_verdict_outcome(name, unit_text, dropin_texts, want_outcome, want_reason_contains):
    outcome, reason = execstart_verdict(unit_text, dropin_texts)
    assert outcome == want_outcome, f"{name}: {reason!r}"
    for token in want_reason_contains:
        assert token.lower() in reason.lower(), f"{name}: {token!r} not in {reason!r}"


# ================================================================== path_presence_verdict
INDEX_HTML = "/srv/kiosk/index.html"


@pytest.mark.parametrize(
    ("name", "present", "required", "want_outcome", "want_reason_contains"),
    [
        ("single path present is ok", {INDEX_HTML}, (INDEX_HTML,), "ok", ()),
        ("single path absent, named", set(), (INDEX_HTML,), "error", (INDEX_HTML,)),
    ],
)
def test_path_presence_verdict_outcome(name, present, required, want_outcome, want_reason_contains):
    outcome, reason = path_presence_verdict(present, required)
    assert outcome == want_outcome, f"{name}: {reason!r}"
    for token in want_reason_contains:
        assert token in reason, f"{name}: {token!r} not in {reason!r}"
