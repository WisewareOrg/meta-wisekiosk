#!/bin/bash
# Writes build/coldbuild/zz-coldbuild.yaml if it is not already there: TMPDIR,
# SSTATE_DIR and BUILDHISTORY_DIR redirected under build/coldbuild/, following
# tools/rauc-rotate-build.sh's ${TOPDIR} overlay precedent. DL_DIR is left at
# its default; zz- sorts this block after every other local_conf_header name.
# Shared by proofs.sh and run-cold-build.sh; not meant to be run by hand.
set -euo pipefail

REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$REPO"

KCONFIG=kiosk-zero-w.yaml
OVERLAY=build/coldbuild/zz-coldbuild.yaml
mkdir -p build/coldbuild
if [ -f "$OVERLAY" ]; then
    exit 0
fi

HDR_VERSION=$(sed -n 's/^[[:space:]]*version:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$KCONFIG" | head -1)
: "${HDR_VERSION:=20}"
cat > "$OVERLAY" <<YAML
header:
  version: $HDR_VERSION
local_conf_header:
  zz-coldbuild: |
    TMPDIR = "\${TOPDIR}/coldbuild/tmp"
    SSTATE_DIR = "\${TOPDIR}/coldbuild/sstate-cache"
    BUILDHISTORY_DIR = "\${TOPDIR}/coldbuild/buildhistory"
YAML
