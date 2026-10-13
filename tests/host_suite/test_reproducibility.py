"""Host suite: the rootfs the build hook produced is attributable to this commit."""

import subprocess

ROOTFS = (
    "build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/"
    "core-image-base-raspberrypi0-wifi.rootfs.ext4"
)


def test_reproducibility_gate():
    """The build hook's rootfs names a clean, pushed HEAD (reproducibility-gate.sh)."""
    result = subprocess.run(["tools/reproducibility-gate.sh", "--image", ROOTFS], check=False)
    assert result.returncode == 0
