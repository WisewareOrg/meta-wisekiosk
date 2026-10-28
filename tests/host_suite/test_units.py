"""Host suite: every unit this layer ships resolves the way systemd 255.22 reads it."""

import shutil

from unit_files import check_image, debugfs_lookup, debugfs_read, shipped_units

ROOTFS = (
    "build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/"
    "core-image-base-raspberrypi0-wifi.rootfs.ext4"
)


def test_units_resolve_in_the_image():
    """check_image finds nothing wrong with any unit this layer's recipes ship."""
    assert shutil.which("debugfs") is not None, "debugfs is not on PATH"
    unit_names = shipped_units()
    assert unit_names, "no shipped units found -- the glob in shipped_units() is broken"
    assert check_image(unit_names, debugfs_lookup(ROOTFS), debugfs_read(ROOTFS)) == []
