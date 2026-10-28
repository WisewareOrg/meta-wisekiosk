"""Host suite: every unit this layer ships verifies and is enabled the way systemd reads it.

systemd-analyze verify and systemctl is-enabled read the unpacked rootfs directly, in place
of a hand-rolled unit parser. --recursive-errors=no is load-bearing: without it, verify
fails a unit over a generator-produced dependency (data.mount, from /etc/fstab) that a
static extracted tree never has, even though the named unit itself is fine.
"""

import glob
import shutil
import subprocess
from pathlib import Path

ROOTFS_TARBALL = (
    "build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/"
    "core-image-base-raspberrypi0-wifi.rootfs.tar.bz2"
)


def shipped_units():
    """List the basenames of every unit/timer file this layer's recipes ship."""
    root = Path(__file__).resolve().parent.parent.parent
    names = []
    for pattern in ("*.service", "*.timer"):
        matches = glob.glob(str(root / "meta-wisekiosk" / "recipes-*" / "**" / pattern), recursive=True)
        names += [Path(match).name for match in matches]
    return names


def test_units_verify_and_are_enabled(tmp_path):
    """Every shipped unit passes `systemd-analyze verify` and reports enabled or static."""
    for tool in ("systemd-analyze", "systemctl", "tar"):
        assert shutil.which(tool) is not None, f"{tool} is not on PATH"

    unit_names = shipped_units()
    assert unit_names, "no shipped units found -- the glob in shipped_units() is broken"

    rootfs = tmp_path / "rootfs"
    rootfs.mkdir()
    subprocess.run(
        ["tar", "--exclude=./dev", "-xjf", ROOTFS_TARBALL, "-C", str(rootfs)], check=True
    )

    failures = []
    for unit in unit_names:
        verify = subprocess.run(
            ["systemd-analyze", "verify", f"--root={rootfs}", "--recursive-errors=no", unit],
            capture_output=True,
            text=True,
            check=False,
        )
        if verify.returncode != 0:
            failures.append(f"{unit}: verify exited {verify.returncode}: {verify.stdout}{verify.stderr}")
            continue

        enabled = subprocess.run(
            ["systemctl", f"--root={rootfs}", "is-enabled", unit],
            capture_output=True,
            text=True,
            check=False,
        )
        # A unit with no [Install] reports "static", not "enabled" -- both pass. Known
        # limit: is-enabled matches the .wants/.requires entry by name, never its target.
        state = enabled.stdout.strip()
        if state not in ("enabled", "static"):
            failures.append(f"{unit}: is-enabled reported {state!r} (rc {enabled.returncode})")

    assert failures == [], "\n".join(failures)
