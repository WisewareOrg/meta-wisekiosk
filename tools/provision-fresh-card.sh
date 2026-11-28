#!/usr/bin/env bash
# Mount a fresh card's /data, provision it from secrets.yaml, unmount.
#
#   tools/provision-fresh-card.sh <device> <mountpoint>
#
# /data is partition 4: /dev/sdX takes a bare 4, mmcblk and nvme interpose a `p`. The partition is
# unmounted on every exit path. The provisioning itself is `tools/provision.sh card`.
#
# Exit: 0 provisioned and unmounted; 2 an argument missing; 1 any failure.
set -uo pipefail

usage() {
    echo "usage: provision-fresh-card.sh <device> <mountpoint>" >&2
    exit 2
}

if [ "$#" -ne 2 ]; then
    usage
fi
DEVICE=$1 MOUNTPOINT=$2
ROOT=$(cd "$(dirname "$0")/.." && pwd)

# sudo consults SUDO_ASKPASS only under -A.
if [ -n "${SUDO_ASKPASS:-}" ]; then SUDO=(sudo -A); else SUDO=(sudo); fi
case "$DEVICE" in
    *mmcblk*|*nvme*) PART="${DEVICE}p4" ;;
    *)               PART="${DEVICE}4"  ;;
esac
if [ ! -b "$PART" ]; then
    echo "Error: $PART is not a block device -- flash the card first, and check the device name"
    exit 1
fi
"${SUDO[@]}" mkdir -p "$MOUNTPOINT"
"${SUDO[@]}" mount "$PART" "$MOUNTPOINT" || { echo "could not mount $PART"; exit 1; }
trap '"${SUDO[@]}" umount "$MOUNTPOINT" || echo "WARNING: $MOUNTPOINT is still mounted"' EXIT
# sudo resets HOME, so the secrets path is resolved as the invoking user and passed through.
"${SUDO[@]}" KIOSK_SECRETS="${KIOSK_SECRETS:-$HOME/.config/wisekiosk/secrets.yaml}" "$ROOT/tools/provision.sh" card "$MOUNTPOINT"
