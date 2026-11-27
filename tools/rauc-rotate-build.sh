#!/bin/bash
# Build the two RAUC bundles a signing-key rotation needs:
#   new-signed.raucb  - rootfs carrying the NEW keyring, signed with the NEW key.
#   transition.raucb  - the same rootfs (NEW keyring), signed with the OLD key.
#
# Both bundles bake the same keyring; the second build only re-runs the signing step.
# rauc-rotate.sh installs them in order.
#
# Usage: rauc-rotate-build.sh <new-keydir> [kas-config]
#   new-keydir - dir holding signing.key.pem + signing.cert.pem (from rauc-keygen.sh)
set -euo pipefail

NEW_KEYDIR=${1:?usage: rauc-rotate-build.sh <new-keydir> [kas-config]}
KCONFIG=${2:-kiosk-zero-w.yaml}

REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"

# OLD_KEYDIR holds the key the fleet trusts; 'just rotate-build' passes it in from fleet-key.
# An explicit test, not ${OLD_KEYDIR:?msg}, whose message word is expanded.
if [ -z "${OLD_KEYDIR:-}" ]; then
    echo "OLD_KEYDIR not set -- run 'just rotate-build <new-key-name>', or set it" >&2
    echo "to the keydir holding the key the fleet currently trusts." >&2
    exit 1
fi
OLD_KEY="$OLD_KEYDIR/signing.key.pem"
OLD_CERT="$OLD_KEYDIR/signing.cert.pem"

test -f "$NEW_KEYDIR/signing.key.pem"  || { echo "no signing.key.pem in $NEW_KEYDIR" >&2; exit 1; }
test -f "$NEW_KEYDIR/signing.cert.pem" || { echo "no signing.cert.pem in $NEW_KEYDIR" >&2; exit 1; }
test -f "$OLD_KEY"  || { echo "current fleet key not found ($OLD_KEY) -- set OLD_KEYDIR" >&2; exit 1; }
test -f "$OLD_CERT" || { echo "current fleet cert not found ($OLD_CERT) -- set OLD_KEYDIR" >&2; exit 1; }

# Compares resolved paths, so local/keys/x and ./local/keys/x are one directory.
if [ "$(realpath -- "$NEW_KEYDIR")" = "$(realpath -- "$OLD_KEYDIR")" ]; then
    echo "refusing: new keydir and old keydir are the same directory" >&2
    echo "  both resolve to $(realpath -- "$NEW_KEYDIR")" >&2
    echo "a rotation needs a NEW key -- generate one with 'just rotate-keygen <name>'," >&2
    echo "then 'just rotate-build <name>'." >&2
    exit 1
fi

# Both keys are staged in one gitignored directory under build/, referenced as ${TOPDIR}/... so it
# resolves inside and outside the container.
OUT="build/rotation"
STAGE="$OUT/keydir"
mkdir -p "$STAGE"
# Modes 700/600 match local/keys/<name>.
chmod 700 "$STAGE"
install -m600 "$NEW_KEYDIR/signing.key.pem"  "$STAGE/signing.key.pem"
install -m644 "$NEW_KEYDIR/signing.cert.pem" "$STAGE/signing.cert.pem"
install -m600 "$OLD_KEY"  "$STAGE/old.key.pem"
install -m644 "$OLD_CERT" "$STAGE/old.cert.pem"

HDR_VERSION=$(sed -n 's/^[[:space:]]*version:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$KCONFIG" | head -1)
: "${HDR_VERSION:=14}"

BUNDLE_LINK="build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/update-bundle-raspberrypi0-wifi.raucb"

# $1 out-file  $2 signing-key filename  $3 signing-cert filename. The baked keyring is always the
# NEW cert; only the signer differs. kas applies local_conf_header blocks in key order, so the
# zz- prefix sorts this one last.
gen_override() {
    cat > "$1" <<YAML
header:
  version: $HDR_VERSION
local_conf_header:
  zz-rauc-rotation: |
    AUTONOMOS_RAUC_KEY_DIR = "\${TOPDIR}/rotation/keydir"
    AUTONOMOS_RAUC_KEY_FILE = "$2"
    AUTONOMOS_RAUC_CERT_FILE = "$3"
    AUTONOMOS_RAUC_KEYRING_FILE = "signing.cert.pem"
YAML
}

echo "== build A: end-state bundle (new keyring, NEW-signed)"
gen_override "$OUT/override-endstate.yaml" signing.key.pem signing.cert.pem
tools/kas-run.sh shell "$KCONFIG:$OUT/override-endstate.yaml" -c "bitbake update-bundle"
test -f "$BUNDLE_LINK" || { echo "build A produced no bundle at $BUNDLE_LINK" >&2; exit 1; }
cp -L "$BUNDLE_LINK" "$OUT/new-signed.raucb"

echo "== build B: transition bundle (new keyring, OLD-signed)"
gen_override "$OUT/override-transition.yaml" old.key.pem old.cert.pem
tools/kas-run.sh shell "$KCONFIG:$OUT/override-transition.yaml" -c "bitbake update-bundle"
test -f "$BUNDLE_LINK" || { echo "build B produced no bundle at $BUNDLE_LINK" >&2; exit 1; }
cp -L "$BUNDLE_LINK" "$OUT/transition.raucb"

# The keyring baked into the rootfs must be the NEW cert. The signer is checked by the `rauc info`
# gate inside kiosk-install.
ROOTFS="build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/core-image-base-raspberrypi0-wifi.rootfs.ext4"
NEW_FP=$(openssl x509 -in "$STAGE/signing.cert.pem" -noout -fingerprint -sha256 | sed 's/.*=//')
if command -v debugfs >/dev/null 2>&1 && [ -f "$ROOTFS" ]; then
    BAKED_FP=$(debugfs -R "cat /etc/rauc/keyring.pem" "$ROOTFS" 2>/dev/null \
        | openssl x509 -noout -fingerprint -sha256 2>/dev/null | sed 's/.*=//')
    if [ "$BAKED_FP" = "$NEW_FP" ]; then
        echo "verified: rootfs keyring == new cert ($BAKED_FP)"
    else
        echo "FAIL: rootfs keyring is $BAKED_FP, expected new cert $NEW_FP" >&2
        echo "the key override did not apply -- do NOT deploy these bundles." >&2
        exit 1
    fi
else
    echo "note: debugfs unavailable or rootfs missing; skipping baked-keyring check"
    echo "      (the phase-1 fingerprint gate on-device still catches a wrong keyring)"
fi

echo
echo "built:"
echo "  $OUT/new-signed.raucb   (NEW-signed; the end state)"
echo "  $OUT/transition.raucb   (OLD-signed; install first on an old-key device)"
echo "next: just rotate-run root@<host> $(basename "$NEW_KEYDIR")"
