#!/bin/bash
# Build the two bundles the refused-update tests offer, inside the kas container.
#
# Usage: refused_bundles.sh <run-dir> <board-compatible>
#   run-dir           holds foreign-key/signing.{key,cert}.pem; receives the two bundles
#   board-compatible  the compatible the board reports
set -euo pipefail

run_dir=${1:?usage: refused_bundles.sh <run-dir> <board-compatible>}
board_compatible=${2:?usage: refused_bundles.sh <run-dir> <board-compatible>}

# A sibling machine's compatible, as its `system.conf` in meta-autonomos-raspberrypi carries it.
other_hardware_compatible=autonomos-raspberrypi-zero-2w

# An operator-signed bundle carrying the board's own compatible would be accepted by the fleet.
if [ "$board_compatible" = "$other_hardware_compatible" ]; then
    echo "refused_bundles.sh: the board's compatible is the other-hardware one" >&2
    exit 1
fi

cd "$run_dir"
bitbake -e update-bundle > bitbake-env.txt
bb_var() { sed -n "s/^$1=\"\(.*\)\"$/\1/p" bitbake-env.txt; }
rauc_bin="$(bb_var STAGING_BINDIR_NATIVE)"
operator_key="$(bb_var RAUC_KEY_FILE)"
operator_cert="$(bb_var RAUC_CERT_FILE)"
: "${rauc_bin:?}" "${operator_key:?}" "${operator_cert:?}"
export PATH="$rauc_bin:$PATH"

# 1 MiB of random bytes: `rauc bundle` refuses a compressible payload, which squashes to 4096 bytes.
stage() {
    mkdir "$1"
    printf '[update]\ncompatible=%s\n[bundle]\nformat=verity\n[image.rootfs]\nfilename=rootfs.ext4\n' \
        "$2" > "$1/manifest.raucm"
    head -c 1048576 /dev/urandom > "$1/rootfs.ext4"
}

# signed by a key no operator holds; the board's own compatible
stage foreign-signature "$board_compatible"
rauc bundle --cert=foreign-key/signing.cert.pem --key=foreign-key/signing.key.pem \
    foreign-signature foreign-signature.raucb

# signed by the operator; never the board's compatible
stage other-hardware "$other_hardware_compatible"
rauc bundle --cert="$operator_cert" --key="$operator_key" other-hardware other-hardware.raucb
