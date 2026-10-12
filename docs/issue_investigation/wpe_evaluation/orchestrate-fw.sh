#!/bin/bash
# orchestrate-fw.sh -- waits for the 138d914 build and for the v3 analysis to free the lock,
# then: OTA+verify (under lock), a one-shot fwgrab/drmgrab sanity pass (under lock, stops
# here if fwgrab fails), the 90+90 fw/drm burst capture (under lock), then the tile-flip
# analysis. Each phase gets its own LOG/.done pair.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
# Self .done: EVERY orchestrator writes its own top-level .log.done as its last act,
# in an EXIT trap so it fires on an early abort too -- a waiter blocks on this file,
# not on an outer wrapper that may not exist.
trap 'touch "$LOGDIR/orchestrate-fw.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}

echo "--- waiting for build-138d914.log.done ---"
until [ -f "$LOGDIR/build-138d914.log.done" ]; do sleep 10; done
if ! grep -q "BUILD_EXIT=0" "$LOGDIR/build-138d914.log"; then
	echo "ABORT: build did not succeed, see $LOGDIR/build-138d914.log"
	exit 1
fi
echo "build OK"

echo "--- phase 2: OTA + verify (under lock) ---"
OTA_LOG="$LOGDIR/ota-verify-138d914.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-138d914.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: ota-verify failed rc=$OTA_RC, see $OTA_LOG"
	exit 1
fi
echo "ota-verify OK"

echo "--- phase 3: fwgrab sanity pass (under lock) ---"
SANITY_LOG="$LOGDIR/sanity-fwgrab.log"
rm -f "$SANITY_LOG" "$SANITY_LOG.done"
flock "$LOCK" "$BURST/sanity-fwgrab.sh" "$T" > "$SANITY_LOG" 2>&1
SANITY_RC=$?
touch "$SANITY_LOG.done"
if [ $SANITY_RC -ne 0 ]; then
	echo "ABORT: kiosk-fwgrab sanity check failed rc=$SANITY_RC, see $SANITY_LOG"
	exit 1
fi
echo "sanity OK"

echo "--- phase 4: fw/drm burst capture (under lock) ---"
BURST_LOG="$LOGDIR/fw-burst.log"
rm -f "$BURST_LOG" "$BURST_LOG.done"
flock "$LOCK" "$BURST/run-fw-burst-capture.sh" "$T" "$BURST/data-fw" > "$BURST_LOG" 2>&1
BURST_RC=$?
touch "$BURST_LOG.done"
if [ $BURST_RC -ne 0 ]; then
	echo "ABORT: fw burst capture failed rc=$BURST_RC, see $BURST_LOG"
	exit 1
fi
if ! grep -q "FW_BURST_CAPTURE_DONE" "$BURST_LOG"; then
	echo "ABORT: fw burst capture did not reach its end marker, see $BURST_LOG"
	exit 1
fi
echo "fw burst capture OK"

echo "--- phase 5: tile-flip analysis ---"
ANALYSIS_LOG="$LOGDIR/analysis-fw.log"
rm -f "$ANALYSIS_LOG" "$ANALYSIS_LOG.done"
{
	echo "=== FIRMWARE (dispmanx) ==="
	fw_dirs=$(ls -d "$BURST/data-fw"/fw-*/ 2>/dev/null | sort -t- -k2 -n)
	python3 "$BURST/analyze_fw_burst.py" firmware fw $fw_dirs
	echo
	echo "=== DRM (scanout) ==="
	drm_dirs=$(ls -d "$BURST/data-fw"/drm-*/ 2>/dev/null | sort -t- -k2 -n)
	python3 "$BURST/analyze_fw_burst.py" drm drm $drm_dirs
} > "$ANALYSIS_LOG" 2>&1
touch "$ANALYSIS_LOG.done"

echo ORCHESTRATE_FW_DONE
