#!/bin/bash
# orchestrate-254-load.sh -- back to 2.54 (138d914, already built in the sibling worktree) for
# the same 3-phase CPU-load experiment as the 2.44.4 reference. Waits for
# orchestrate-244-load.log.done, verifies the already-built bundle's `compatible` against the
# device's own (via unsquashfs -- no local rauc binary) and logs its version/build before
# installing, then OTA+verify (reusing ota-verify-138d914.sh), then the load experiment, then
# per-phase analysis. Self .done in an EXIT trap from the start.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-254-load.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
IMG=254
WORKTREE=/home/tjwise/meta-wisekiosk-185-254
BUNDLE="$WORKTREE/build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/update-bundle-raspberrypi0-wifi.raucb"

echo "--- waiting for orchestrate-244-load.log.done ---"
until [ -f "$LOGDIR/orchestrate-244-load.log.done" ]; do sleep 10; done
if ! grep -q "ORCHESTRATE_244_LOAD_DONE" "$LOGDIR/orchestrate-244-load.log"; then
	echo "ABORT: 2.44 load experiment did not complete cleanly, see $LOGDIR/orchestrate-244-load.log"
	exit 1
fi
echo "2.44 load experiment OK"

echo "--- verify the built 138d914 bundle before installing ---"
if [ ! -e "$BUNDLE" ]; then
	echo "ABORT: no bundle at $BUNDLE"
	exit 1
fi
RESOLVED=$(readlink -f "$BUNDLE")
echo "bundle: $BUNDLE -> $RESOLVED"
EXTRACT_DIR=$(mktemp -d)
if ! unsquashfs -d "$EXTRACT_DIR/squashfs-root" "$BUNDLE" manifest.raucm > /dev/null 2>&1; then
	echo "ABORT: could not read manifest.raucm out of the bundle (unsquashfs failed)"
	rm -rf "$EXTRACT_DIR"
	exit 1
fi
MANIFEST="$EXTRACT_DIR/squashfs-root/manifest.raucm"
echo "--- manifest.raucm ---"
cat "$MANIFEST"
BUNDLE_COMPATIBLE=$(sed -n 's/^compatible=//p' "$MANIFEST")
BUNDLE_VERSION=$(sed -n 's/^version=//p' "$MANIFEST")
BUNDLE_BUILD=$(sed -n 's/^build=//p' "$MANIFEST")
rm -rf "$EXTRACT_DIR"
echo "bundle compatible=$BUNDLE_COMPATIBLE version=$BUNDLE_VERSION build=$BUNDLE_BUILD"

DEVICE_COMPATIBLE=$(/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh "$T" 'rauc status' | sed -n 's/^Compatible:\s*//p')
echo "device compatible=$DEVICE_COMPATIBLE"
if [ -z "$BUNDLE_COMPATIBLE" ] || [ "$BUNDLE_COMPATIBLE" != "$DEVICE_COMPATIBLE" ]; then
	echo "ABORT: bundle compatible '$BUNDLE_COMPATIBLE' does not match device compatible '$DEVICE_COMPATIBLE'"
	exit 1
fi
echo "COMPATIBLE_MATCH"

echo "--- OTA + verify 138d914 (under lock) ---"
OTA_LOG="$LOGDIR/ota-verify-138d914-2.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-138d914.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: ota-verify failed rc=$OTA_RC, see $OTA_LOG"
	exit 1
fi
echo "ota-verify OK"

echo "--- load experiment (under lock) ---"
LOAD_LOG="$LOGDIR/load-$IMG.log"
rm -f "$LOAD_LOG" "$LOAD_LOG.done"
flock "$LOCK" "$BURST/run-load-experiment.sh" "$T" "$BURST/data-load-$IMG" "$IMG" > "$LOAD_LOG" 2>&1
LOAD_RC=$?
touch "$LOAD_LOG.done"
if [ $LOAD_RC -ne 0 ]; then
	echo "ABORT: load experiment failed rc=$LOAD_RC, see $LOAD_LOG"
	exit 1
fi
if ! grep -q "LOAD_EXPERIMENT_DONE" "$LOAD_LOG"; then
	echo "ABORT: load experiment did not reach its end marker, see $LOAD_LOG"
	exit 1
fi
echo "load experiment OK"

echo "--- analysis, per phase ---"
ANALYSIS_LOG="$LOGDIR/analysis-load-$IMG.log"
rm -f "$ANALYSIS_LOG" "$ANALYSIS_LOG.done"
{
	for phase in idle spinner drmloop; do
		echo "=== $IMG / $phase ==="
		dirs=$(ls -d "$BURST/data-load-$IMG"/"$phase"-*/ 2>/dev/null | sort -V)
		python3 "$BURST/analyze_fw_burst.py" "$IMG-$phase" fw $dirs
		echo
	done
} > "$ANALYSIS_LOG" 2>&1
touch "$ANALYSIS_LOG.done"

echo ORCHESTRATE_254_LOAD_DONE
