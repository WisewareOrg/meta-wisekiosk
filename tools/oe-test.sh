#!/usr/bin/env bash
# Hand-run path for the wisekiosk oeqa suite: the same cases and the same
# run record `testimage` produces in the pipeline, run with `oe-test runtime`
# against any reachable target -- no bitbake, no OTA.
#
#   tools/oe-test.sh <target-ip>
#
# KIOSK_TARGET_ROLE and KIOSK_TARGET_HOSTNAME are resolved from
# local/device-identity.md: the role (prod or bench) whose recorded address
# equals <target-ip>, and bench's own recorded hostname -- the suite refuses
# any board that is not bench, so the expected hostname is always bench's.
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

KEY="$ROOT/local/hmac.key"
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

# Resolves the two identity env vars through tools/scrub-identity.py's own
# fenced-block parser (never a copy of it): prod and bench are the only two
# documented roles, so only their .address keys are candidates.
IDENTITY=$(python3 -c '
import importlib.util
import sys
from pathlib import Path

root, target = Path(sys.argv[1]), sys.argv[2]
spec = importlib.util.spec_from_file_location(
    "scrub_identity", root / "tools" / "scrub-identity.py")
scrub_identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scrub_identity)

rows = dict(scrub_identity._map_rows(scrub_identity.map_path(root)))

hostname = rows.get("bench.hostname")
if not hostname:
    sys.exit("oe-test.sh: local/device-identity.md has no bench.hostname")

role = next((r for r in ("prod", "bench") if rows.get(r + ".address") == target), None)
if role is None:
    sys.exit("oe-test.sh: no role in local/device-identity.md has address %s" % target)

print("KIOSK_TARGET_ROLE=%s" % role)
print("KIOSK_TARGET_HOSTNAME=%s" % hostname)
' "$ROOT" "$TARGET") || exit 1
eval "$IDENTITY"
export KIOSK_TARGET_ROLE KIOSK_TARGET_HOSTNAME

# sources/poky/bitbake/lib is needed in addition to meta/lib: oe-test's own
# component loader imports every subcommand's context module up front, and
# oeqa.selftest.context imports bb.utils at module scope regardless of which
# subcommand (runtime) is actually requested.
export PYTHONPATH="$POKY/meta/lib:$POKY/bitbake/lib:$ROOT/meta-wisekiosk/lib"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RESULT_DIR="$ROOT/local/oe-test/$STAMP"
mkdir -p "$RESULT_DIR"

exec python3 "$POKY/scripts/oe-test" runtime "$ROOT/meta-wisekiosk/lib/oeqa/runtime/cases" \
    --test-data-file "$TESTDATA" \
    --packages-manifest "$MANIFEST" \
    --target-type simpleremote \
    --target-ip "$TARGET" \
    --run-tests wisekiosk \
    --json-result-dir "$RESULT_DIR" \
    --output-log "$RESULT_DIR/oe-test.log"
