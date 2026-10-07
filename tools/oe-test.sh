#!/usr/bin/env bash
# Hand-run path for the kiosk oeqa suite, against any reachable target --
# no bitbake, no OTA. docs/testing.md § "The hand-run path" has the why.
#
#   tools/oe-test.sh <target-ip>
#
# Env: OE_TEST_TESTDATA, OE_TEST_MANIFEST override the last build's own
# .testdata.json/.manifest symlinks under the deploy directory.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

if [ -z "${1:-}" ]; then
    echo "usage: oe-test.sh <target-ip>" >&2
    exit 2
fi
TARGET=$1

KEY="$ROOT/local/keys/hmac.key"
if [ ! -f "$KEY" ]; then
    echo "oe-test.sh: no $KEY -- run 'just pipeline-install' first" >&2
    exit 1
fi

MAP="$ROOT/local/device-identity.md"
if [ ! -f "$MAP" ]; then
    echo "oe-test.sh: no $MAP -- see CONTRIBUTING.md" >&2
    exit 1
fi

POKY="$ROOT/sources/poky"
if [ ! -d "$POKY" ]; then
    echo "oe-test.sh: no $POKY -- has kas fetched sources/ yet? (just build)" >&2
    exit 1
fi

DEPLOY="$ROOT/build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi"
TESTDATA="${OE_TEST_TESTDATA:-$DEPLOY/core-image-base-raspberrypi0-wifi.rootfs.testdata.json}"
MANIFEST="${OE_TEST_MANIFEST:-$DEPLOY/core-image-base-raspberrypi0-wifi.rootfs.manifest}"
if [ ! -f "$TESTDATA" ]; then
    echo "oe-test.sh: no $TESTDATA -- build first (just build)" >&2
    exit 1
fi
if [ ! -f "$MANIFEST" ]; then
    echo "oe-test.sh: no $MANIFEST -- build first (just build)" >&2
    exit 1
fi

# Resolves the role and hostname through tools/device-role.py, then
# refuses outright on anything but bench: this suite never runs against
# prod, by direct check here rather than relying only on the base class's
# live-hostname comparison.
ROLE_LINE=$(python3 "$ROOT/tools/device-role.py" "$TARGET") || exit 1
read -r ROLE_KV HOSTNAME_KV <<< "$ROLE_LINE"
KIOSK_TARGET_ROLE=${ROLE_KV#role=}
KIOSK_TARGET_HOSTNAME=${HOSTNAME_KV#hostname=}
if [ "$KIOSK_TARGET_ROLE" != "bench" ]; then
    echo "oe-test.sh: $TARGET resolves to role=$KIOSK_TARGET_ROLE -- this suite only ever runs against bench" >&2
    exit 1
fi
export KIOSK_TARGET_ROLE KIOSK_TARGET_HOSTNAME
export KIOSK_HMAC_KEY="$KEY"

# poky's own paths only, matching testimage's: the loader inserts the
# cases directory itself as each case's own top_level_dir (so kiosk,
# kiosk_render etc. resolve as bare top-level packages there, never
# oeqa.runtime.cases.*), and meta-wisekiosk/lib on PYTHONPATH masks that --
# namespace-package merging would let the nested form resolve too, passing
# a case.py testimage itself would refuse. docs/testing.md § "The hand-run
# path" has the why.
export PYTHONPATH="$POKY/meta/lib:$POKY/bitbake/lib"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RESULT_DIR="$ROOT/local/oe-test/$STAMP"
mkdir -p "$RESULT_DIR"

# Every other path above is already absolute, so cwd is free to move.
# docs/testing.md § "The hand-run path" has the why.
cd "$RESULT_DIR" || exit 1

exec python3 "$POKY/scripts/oe-test" runtime "$ROOT/meta-wisekiosk/lib/oeqa/runtime/cases" \
    --test-data-file "$TESTDATA" \
    --packages-manifest "$MANIFEST" \
    --target-type simpleremote \
    --target-ip "$TARGET" \
    --run-tests kiosk_backend_unit kiosk_healthz_bound kiosk_page_serves kiosk_health_flag kiosk_render kiosk_applied \
    --json-result-dir "$RESULT_DIR" \
    --output-log "$RESULT_DIR/oe-test.log"
