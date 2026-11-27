#!/bin/bash
# Generate a per-project RAUC signing key + self-signed certificate under the
# gitignored local/keys/<name>. The certificate becomes the device keyring;
# the key signs update bundles.
#
# Usage: rauc-keygen.sh <outdir> [common-name]
#   outdir  - directory to create the pair in (refused if it already holds one)
#   common-name - certificate CN (default derived from the outdir basename)
set -euo pipefail

OUTDIR=${1:?usage: rauc-keygen.sh <outdir> [common-name]}

# The CN strips a leading "kiosk-" from the directory name; a name without it is used as given.
NAME=$(basename "$OUTDIR")
CN=${2:-"WiseKiosk Signing Key ${NAME#kiosk-}"}

KEY="$OUTDIR/signing.key.pem"
CERT="$OUTDIR/signing.cert.pem"

if [ -e "$KEY" ] || [ -e "$CERT" ]; then
    echo "refusing to overwrite existing key material in $OUTDIR" >&2
    echo "  ($KEY / $CERT) -- rotate into a fresh directory instead" >&2
    exit 1
fi

mkdir -p "$OUTDIR"
chmod 700 "$OUTDIR"

# 4096-bit RSA, self-signed, 10-year validity.
openssl req -x509 -newkey rsa:4096 -nodes \
    -keyout "$KEY" -out "$CERT" \
    -days 3650 -sha256 \
    -subj "/CN=$CN/O=WiseKiosk/C=US" >/dev/null 2>&1

chmod 600 "$KEY"
chmod 644 "$CERT"

FP=$(openssl x509 -in "$CERT" -noout -fingerprint -sha256 | sed 's/.*=//')
echo "generated RAUC signing pair:"
echo "  key  : $KEY"
echo "  cert : $CERT"
echo "  CN   : $CN"
echo "  sha256 fingerprint: $FP"
