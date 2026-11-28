#!/usr/bin/env bash
# Flash the WIC image to an SD card, once the image is shown to bake the fleet keyring.
#
#   tools/flash.sh <device> <wic.bz2> <rootfs.ext4> <fleet-cert>
#
# Checks, in order: the device is a block device; the image exists; the .ext4 and the .wic.bz2 come
# from one build (their timestamps match); the keyring baked into the .ext4 has the fleet cert's
# fingerprint; the reproducibility gate on the .ext4. It then asks before it writes with bmaptool,
# or bzcat and dd without it, and re-reads the partition table. A wrong keyring cannot be repaired
# over the air, so every check fails closed.
#
# Exit: 0 flashed; 2 an argument missing; 1 any refusal or failure.
set -euo pipefail

usage() {
    awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
}

if [ "$#" -ne 4 ]; then
    usage >&2
    exit 2
fi
DEVICE=$1 IMAGE=$2 ROOTFS=$3 FLEET_CERT=$4
ROOT=$(cd "$(dirname "$0")/.." && pwd)

# sudo consults SUDO_ASKPASS only under -A.
if [ -n "${SUDO_ASKPASS:-}" ]; then SUDO=(sudo -A); else SUDO=(sudo); fi
if [ ! -b "$DEVICE" ]; then
    echo "Error: Device not found or not a block device: $DEVICE"
    exit 1
fi
if [ ! -f "$IMAGE" ]; then
    echo "Error: Image not found: $IMAGE"
    echo "Did you run 'just build' first?"
    exit 1
fi

# Fails closed: refuses unless the rootfs keyring matches the fleet cert.
test -f "$FLEET_CERT" || { echo "Error: fleet cert not found: $FLEET_CERT" >&2; exit 1; }
test -f "$ROOTFS"     || { echo "Error: rootfs not found: $ROOTFS" >&2; exit 1; }
command -v debugfs >/dev/null 2>&1 || { echo "Error: debugfs missing -- cannot verify the keyring; refusing to flash" >&2; exit 1; }

# The keyring is read from the .ext4; the shared build timestamp ties it to the .wic.bz2.
# Assumes wic populates the rootfs partition from the tree the .ext4 is generated from.
IMG_STAMP=$(basename "$(readlink -f "$IMAGE")"  | sed -n 's/.*rootfs-\([0-9]\{8,\}\)\..*/\1/p')
EXT_STAMP=$(basename "$(readlink -f "$ROOTFS")" | sed -n 's/.*rootfs-\([0-9]\{8,\}\)\..*/\1/p')
if [ -z "$IMG_STAMP" ] || [ "$IMG_STAMP" != "$EXT_STAMP" ]; then
    echo "Error: cannot tie the rootfs to the image being flashed" >&2
    echo "  image  build: ${IMG_STAMP:-unknown}" >&2
    echo "  rootfs build: ${EXT_STAMP:-unknown}" >&2
    echo "One is stale. Re-run 'just build' so both come from one build." >&2
    exit 1
fi

# errexit off so the empty-result branches below report which input is broken.
set +e
WANT_FP=$(openssl x509 -in "$FLEET_CERT" -noout -fingerprint -sha256 2>/dev/null | sed 's/.*=//')
BAKED_PEM=$(debugfs -R "cat /etc/rauc/keyring.pem" "$ROOTFS" 2>/dev/null)
BAKED_FP=$(printf '%s\n' "$BAKED_PEM" \
    | openssl x509 -noout -fingerprint -sha256 2>/dev/null | sed 's/.*=//')
set -e

# `|| true` keeps pipefail from aborting the diagnostic; head bounds the tool output.
if [ -z "$WANT_FP" ]; then
    echo "-- openssl reported: --" >&2
    { openssl x509 -in "$FLEET_CERT" -noout -fingerprint -sha256 2>&1 >/dev/null | head -3 >&2; } || true
    echo "Error: cannot read a certificate from the fleet cert:" >&2
    echo "  $FLEET_CERT" >&2
    echo "Unparseable -- truncated, empty, or not PEM. Refusing to flash: with" >&2
    echo "no cert there is nothing to verify the card against. Check the file," >&2
    echo "or that fleet-key in the Justfile names the right key." >&2
    exit 1
fi

if [ -z "$BAKED_FP" ]; then
    echo "-- debugfs reported: --" >&2
    { debugfs -R "cat /etc/rauc/keyring.pem" "$ROOTFS" 2>&1 >/dev/null | head -3 >&2; } || true
    echo "Error: no readable certificate at /etc/rauc/keyring.pem in:" >&2
    echo "  $ROOTFS" >&2
    echo "Truncated, not an ext4, or built without the RAUC keyring recipe." >&2
    echo "Refusing to flash: a wrong keyring cannot be repaired over the air." >&2
    exit 1
fi
if [ "$BAKED_FP" != "$WANT_FP" ]; then
    echo "Error: the image does not bake the fleet keyring -- refusing to flash." >&2
    echo "  baked   : $BAKED_FP" >&2
    echo "  expected: $WANT_FP" >&2
    echo "  expected cert: $FLEET_CERT" >&2
    echo "This card would boot a unit that rejects every fleet update, with no" >&2
    echo "OTA repair. Rebuild against the fleet key, or check that fleet-key in" >&2
    echo "the Justfile still names the key the fleet trusts." >&2
    exit 1
fi
echo "verified: image bakes the fleet keyring ($BAKED_FP)"

"$ROOT/tools/reproducibility-gate.sh" --image "$ROOTFS" || exit 1

echo "Flashing $IMAGE to $DEVICE..."
echo "WARNING: This will overwrite all data on $DEVICE!"
# `|| true`: read exits non-zero at EOF; an empty REPLY declines.
read -p "Continue? [y/N] " -n 1 -r || true
echo
if [[ ! ${REPLY:-} =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi
if command -v bmaptool &> /dev/null; then
    BMAP="${IMAGE%.bz2}.bmap"
    if [ -f "$BMAP" ]; then
        "${SUDO[@]}" bmaptool copy --bmap "$BMAP" "$IMAGE" "$DEVICE"
    else
        echo "Warning: bmap file not found, bmaptool will be slower"
        "${SUDO[@]}" bmaptool copy "$IMAGE" "$DEVICE"
    fi
else
    echo "bmaptool not found, falling back to dd (slower)..."
    bzcat "$IMAGE" | "${SUDO[@]}" dd of="$DEVICE" bs=4M status=progress conv=fsync,sparse
fi
sync
# The kernel re-reads the partition table so the new partitions exist as device nodes.
"${SUDO[@]}" blockdev --rereadpt "$DEVICE" || echo "Warning: could not re-read the partition table -- replug the card before provisioning"
udevadm settle 2>/dev/null || true
echo "Done. Safe to eject $DEVICE."
