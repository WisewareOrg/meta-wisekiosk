"""Specifies cases/kiosk_image/verdict.py (#206, step 4 of #202, reduced to the owner's lens --
see ~/.claude/plans/202/step4/brief.md "Subject and size"): the image-content tier's three
surviving parse/judgement functions --

- `execstart_verdict`: the display unit's effective `ExecStart=` (unit + drop-ins, merged as
  systemd merges them) carries `-s 0 -dpms -nocursor`.
- `bundle_image_hash_verdict`: the bundle manifest's rootfs sha256 ties to the deployed `.ext4`.
- `path_presence_verdict`: a path or binary name is present in the image -- used for both
  `/srv/kiosk/index.html` and the four required tool binaries (`xprop`/`xrandr`/`xset`/`import`).

`systemd_analyze_verdict` is NOT tested here: brief.md "Correction" (owner, 2026-10-08) moves the
units-well-formed check to the device tier (`cases/kiosk_units/`, runs `systemd-analyze verify` on
the board, no `--root`) -- its classification tests now live in
`cases/kiosk_units/tests/test_units.py`.

No `self.target`, no subprocess, no network -- every argument below is a plain Python value case.py
is responsible for collecting (through `debugfs`, a rootfs directory walk, or a host subprocess).

Each surviving function gets exactly one parametrized test, one row per code branch (the round-3
dispatch's "cut to one test per branch"): a row whose branch carries a load-bearing message checks
that message's content in the same row, rather than in a separate dedicated test. Two prior-round
rows were dropped as duplicates of a branch already covered, not new coverage: a custom
`execstart_verdict(required=...)` call (same branch as the default, different data) and a
"missing key only" bundle-manifest case (the function's `has_option` check can't distinguish
"section absent" from "key absent" -- both already exercised by one "section absent" row).

Grounded this session against real artifacts on this host, never an invented shape:
- `kiosk.service`'s own real unit text (`meta-wisekiosk/recipes-core/kiosk-session/files/
  kiosk.service`), carrying the real `-s 0 -dpms -nocursor` ExecStart= line this check protects.
- The real `update-bundle-raspberrypi0-wifi.raucb` at the pipeline tree's own populated `build/`
  (`PIPELINE_TREE` in `~/.config/wisekiosk/pipeline.env`), unpacked with `unsquashfs`: its real
  `manifest.raucm` (`[image.rootfs]` section, `sha256=` key, RAUC's own INI shape) carries
  `sha256=be21992502ce2537598b753bf0c1919c984827be6dc4771e486cafede5b6de74`, independently
  confirmed equal to a fresh `sha256sum` of that same build's deployed `.ext4`
  (`core-image-base-raspberrypi0-wifi.rootfs.ext4`).
- `debugfs -R "stat /srv/kiosk/index.html" <ext4>` and `.../usr/bin/{xprop,xrandr,xset}`,
  `.../usr/bin/import` against that same real `.ext4`: every one resolves to a real inode (a
  regular file for the first three binaries and `index.html`, a symlink for `import`) -- `case.py`
  turns a resolved `stat` into "present"; this module's own `path_presence_verdict` takes that
  already-reduced `present` container, not `debugfs` text.
"""

import pytest

from oeqa.runtime.cases.kiosk_image.verdict import (
    REQUIRED_BINARIES,
    REQUIRED_DISPLAY_FLAGS,
    bundle_image_hash_verdict,
    execstart_verdict,
    path_presence_verdict,
)

# ================================================================== execstart_verdict
# The real kiosk.service ExecStart= line this check protects (meta-wisekiosk/recipes-core/
# kiosk-session/files/kiosk.service:18) -- carries every REQUIRED_DISPLAY_FLAGS token.
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

# A unit missing the display flags entirely -- a mutation of the real ExecStart= line above,
# standing in for a regression that drops the flags at the source.
UNIT_MISSING_FLAGS = KIOSK_SERVICE_UNIT.replace(
    "ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1 -s 0 -dpms -nocursor",
    "ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1",
)

# A drop-in that touches only Restart=, never ExecStart= -- systemd's real per-directive
# drop-in shape (a `.service.d/*.conf` snippet), confirming a drop-in with no ExecStart=
# line at all leaves the unit's own ExecStart= untouched.
DROPIN_NO_EXECSTART = """[Service]
Restart=on-failure
"""

# A drop-in resetting ExecStart= (systemd's real "assign the empty string to reset the
# accumulated command list" rule) and replacing it with a command that carries none of the
# required display flags -- the real failure mode a provisioned drop-in could introduce.
DROPIN_RESETS_AND_DROPS_FLAGS = """[Service]
ExecStart=
ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1
"""

# A drop-in resetting ExecStart= and then re-adding every required flag -- proves the merge
# is not "unit's flags always win": a drop-in can both remove and restore them.
DROPIN_RESETS_AND_RESTORES_FLAGS = """[Service]
ExecStart=
ExecStart=/usr/bin/xinit /usr/bin/kiosk-launch -- :0 vt1 -s 0 -dpms -nocursor
"""

# A drop-in that only resets, with nothing after -- the merge's "no ExecStart= survived" case.
DROPIN_RESETS_ONLY = """[Service]
ExecStart=
"""

# A drop-in whose ExecStart=-looking line sits outside [Service] (a constructed, not realistic,
# edge -- but the merge must not pick up a directive from the wrong section).
DROPIN_EXECSTART_OUTSIDE_SERVICE = """[Unit]
ExecStart=/usr/bin/not-a-real-directive-here
"""


@pytest.mark.parametrize(
    ("name", "unit_text", "dropin_texts", "want_outcome", "want_reason_contains"),
    [
        ("unit alone, every flag present", KIOSK_SERVICE_UNIT, [], "ok", ()),
        (
            "unit alone, flags missing, named",
            UNIT_MISSING_FLAGS,
            [],
            "error",
            REQUIRED_DISPLAY_FLAGS,
        ),
        (
            "one drop-in touching only Restart=, unit's own flags stand",
            KIOSK_SERVICE_UNIT,
            [DROPIN_NO_EXECSTART],
            "ok",
            (),
        ),
        (
            "one drop-in resets ExecStart= and drops the flags",
            KIOSK_SERVICE_UNIT,
            [DROPIN_RESETS_AND_DROPS_FLAGS],
            "error",
            (),
        ),
        (
            "one drop-in resets ExecStart= and restores every flag",
            KIOSK_SERVICE_UNIT,
            [DROPIN_RESETS_AND_RESTORES_FLAGS],
            "ok",
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
            "two drop-ins in the OPPOSITE order: restore, then drop -- order is honoured",
            KIOSK_SERVICE_UNIT,
            [DROPIN_RESETS_AND_RESTORES_FLAGS, DROPIN_RESETS_AND_DROPS_FLAGS],
            "error",
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


# ================================================================== bundle_image_hash_verdict
# The real manifest.raucm unpacked (unsquashfs) from update-bundle-raspberrypi0-wifi.raucb at
# the pipeline tree's own populated build/ (PIPELINE_TREE, ~/.config/wisekiosk/pipeline.env) --
# see module docstring. Its sha256= is independently confirmed equal to a fresh sha256sum of
# that same build's own deployed core-image-base-raspberrypi0-wifi.rootfs.ext4.
REAL_MANIFEST = """[update]
compatible=autonomos-raspberrypi0-wifi
version=0.1
description=AutonomOS Update Bundle
build=20261008163357

[bundle]
format=verity

[hooks]
filename=kiosk-slot-hook.sh

[image.rootfs]
sha256=be21992502ce2537598b753bf0c1919c984827be6dc4771e486cafede5b6de74
size=2147483648
filename=core-image-base-raspberrypi0-wifi.rootfs.ext4
hooks=post-install;
"""
REAL_EXT4_SHA256 = "be21992502ce2537598b753bf0c1919c984827be6dc4771e486cafede5b6de74"
_OTHER_SHA256 = "f" * 64

# Section AND key both absent -- `has_option("image.rootfs", "sha256")` returns False either
# way, so "section missing" and "key missing" are the same code branch; one row stands for both.
MANIFEST_NO_ROOTFS_SECTION = REAL_MANIFEST.replace(
    "[image.rootfs]\n"
    "sha256=be21992502ce2537598b753bf0c1919c984827be6dc4771e486cafede5b6de74\n"
    "size=2147483648\n"
    "filename=core-image-base-raspberrypi0-wifi.rootfs.ext4\n"
    "hooks=post-install;\n",
    "",
)
MANIFEST_NOT_INI = "this is not an ini file at all {{{"


@pytest.mark.parametrize(
    ("name", "manifest_text", "ext4_sha256", "want_outcome", "want_reason_contains"),
    [
        ("real hash match is ok", REAL_MANIFEST, REAL_EXT4_SHA256, "ok", ()),
        (
            "hash mismatch, both hashes named",
            REAL_MANIFEST,
            _OTHER_SHA256,
            "error",
            (REAL_EXT4_SHA256, _OTHER_SHA256),
        ),
        (
            "[image.rootfs] sha256= absent (section or key) is error",
            MANIFEST_NO_ROOTFS_SECTION,
            REAL_EXT4_SHA256,
            "error",
            ("sha256",),
        ),
        ("manifest not parseable as INI is error", MANIFEST_NOT_INI, REAL_EXT4_SHA256, "error", ()),
    ],
)
def test_bundle_image_hash_verdict_outcome(name, manifest_text, ext4_sha256, want_outcome, want_reason_contains):
    outcome, reason = bundle_image_hash_verdict(manifest_text, ext4_sha256)
    assert outcome == want_outcome, f"{name}: {reason!r}"
    for token in want_reason_contains:
        assert token in reason, f"{name}: {token!r} not in {reason!r}"


# ================================================================== path_presence_verdict
# `present` stands in for what case.py reduces a resolved `debugfs stat <path>` (a regular file
# or symlink inode, confirmed real for every path below against the pipeline tree's own
# deployed .ext4 -- see module docstring) down to: the set of paths/names found in the image.

INDEX_HTML = "/srv/kiosk/index.html"


@pytest.mark.parametrize(
    ("name", "present", "required", "want_outcome", "want_reason_contains", "want_reason_excludes"),
    [
        ("single path present is ok", {INDEX_HTML}, (INDEX_HTML,), "ok", (), ()),
        ("single path absent, named", set(), (INDEX_HTML,), "error", (INDEX_HTML,), ()),
        ("all binaries present is ok", set(REQUIRED_BINARIES), REQUIRED_BINARIES, "ok", (), ()),
        (
            "present may carry unrelated extra names, still ok",
            set(REQUIRED_BINARIES) | {"bash", "ls", "cat"},
            REQUIRED_BINARIES,
            "ok",
            (),
            (),
        ),
        ("empty required is vacuously ok", set(), (), "ok", (), ()),
        (
            "one binary missing, named exactly -- no others",
            set(REQUIRED_BINARIES) - {"xset"},
            REQUIRED_BINARIES,
            "error",
            ("xset",),
            tuple(set(REQUIRED_BINARIES) - {"xset"}),
        ),
    ],
)
def test_path_presence_verdict_outcome(
    name, present, required, want_outcome, want_reason_contains, want_reason_excludes
):
    outcome, reason = path_presence_verdict(present, required)
    assert outcome == want_outcome, f"{name}: {reason!r}"
    for token in want_reason_contains:
        assert token in reason, f"{name}: {token!r} not in {reason!r}"
    for token in want_reason_excludes:
        assert token not in reason, f"{name}: {token!r} unexpectedly in {reason!r}"


def test_path_presence_verdict_every_binary_missing_names_all_in_required_order():
    # The one branch whose contract is ordering, not mere presence -- not expressible as a
    # plain "contains" row above, so it keeps its own test.
    outcome, reason = path_presence_verdict(set(), REQUIRED_BINARIES)
    assert outcome == "error"
    positions = [reason.index(name) for name in REQUIRED_BINARIES]
    assert positions == sorted(positions)
