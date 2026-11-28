#!/usr/bin/env bash
# Refuse a delivery that cannot work: a missing rootfs image or bundle, a rootfs image that fails
# the reproducibility gate, or one larger than a slot of the board.
#
#   tools/kiosk-preflight.sh root@<host> <image> <bundle>
#
# Checks, in order: both files exist; tools/reproducibility-gate.sh --image on the rootfs image (the
# gate checks the image, not the bundle); the image's size against the board's two slot sizes, read
# in one ssh from /sys/class/block.
#
# Exit: 0 the delivery can work; 2 an argument missing; 1 any refusal.
set -euo pipefail

usage() {
    echo "usage: kiosk-preflight.sh root@<host> <image> <bundle>" >&2
    exit 2
}

if [ -z "${1:-}" ] || [ -z "${2:-}" ] || [ -z "${3:-}" ]; then
    usage
fi
host=$1 image=$2 bundle=$3

root=$(cd "$(dirname "$0")/.." && pwd)

test -f "$image"  || { echo "no rootfs image at $image"; exit 1; }
test -f "$bundle" || { echo "no bundle at $bundle"; exit 1; }
image_bytes=$(stat -Lc %s "$image")

"$root/tools/reproducibility-gate.sh" --image "$image" || exit 1

# Slot sizes from the board's block devices (sector count in 512-byte units).
{ read -r a_sectors; read -r b_sectors; } < <("$root/tools/kiosk-ssh.sh" "$host" 'cat /sys/class/block/mmcblk0p2/size /sys/class/block/mmcblk0p3/size')
a_bytes=$((a_sectors * 512))
b_bytes=$((b_sectors * 512))
echo "rootfs image  : $image_bytes"
echo "slot A / B    : $a_bytes / $b_bytes"
for slot in "$a_bytes" "$b_bytes"; do
    if [ "$image_bytes" -gt "$slot" ]; then
        echo "REFUSING: the image does not fit a $slot-byte slot"
        exit 1
    fi
done
echo "preflight OK"
