#!/bin/bash
# orchestrate-244.sh -- 2.44.4 reference run (image 5ec7f0e, known-good per the owner). Waits
# for the 5ec7f0e build AND for orchestrate-fw.sh to finish (it holds the lock first), then:
# OTA+verify (under lock), the v3 CONTROL-only capture (under lock, 12 min), then the fixed
# tile-grid analysis with late-change exclusion and bounding boxes. Leaves bench on this image
# -- no restore step. Each phase gets its own LOG/.done pair.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
# Self .done: EVERY orchestrator writes its own top-level .log.done as its last act,
# in an EXIT trap so it fires on an early abort too -- a waiter blocks on this file,
# not on an outer wrapper that may not exist.
trap 'touch "$LOGDIR/orchestrate-244.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}

echo "--- waiting for build-5ec7f0e.log.done ---"
until [ -f "$LOGDIR/build-5ec7f0e.log.done" ]; do sleep 10; done
if ! grep -q "BUILD_EXIT=0" "$LOGDIR/build-5ec7f0e.log"; then
	echo "ABORT: build did not succeed, see $LOGDIR/build-5ec7f0e.log"
	exit 1
fi
echo "build OK"

echo "--- waiting for orchestrate-fw.log.done (fw chain must release the lock first) ---"
until [ -f "$LOGDIR/orchestrate-fw.log.done" ]; do sleep 10; done
if ! grep -q "ORCHESTRATE_FW_DONE" "$LOGDIR/orchestrate-fw.log"; then
	echo "ABORT: fw chain did not complete cleanly, see $LOGDIR/orchestrate-fw.log"
	exit 1
fi
echo "fw chain OK"

echo "--- phase 1: OTA + verify (under lock) ---"
OTA_LOG="$LOGDIR/ota-verify-5ec7f0e.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-5ec7f0e.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: ota-verify failed rc=$OTA_RC, see $OTA_LOG"
	exit 1
fi
echo "ota-verify OK"

echo "--- phase 2: v3 control-only capture (under lock, ~12 min) ---"
BURST_LOG="$LOGDIR/burst-v3-244.log"
rm -f "$BURST_LOG" "$BURST_LOG.done"
flock "$LOCK" "$BURST/run-burst-capture-v3-control.sh" "$T" "$BURST/data-v3-244" > "$BURST_LOG" 2>&1
BURST_RC=$?
touch "$BURST_LOG.done"
if [ $BURST_RC -ne 0 ]; then
	echo "ABORT: v3 control capture failed rc=$BURST_RC, see $BURST_LOG"
	exit 1
fi
if ! grep -q "BURST_CAPTURE_V3_CONTROL_DONE" "$BURST_LOG"; then
	echo "ABORT: v3 control capture did not reach its end marker, see $BURST_LOG"
	exit 1
fi
echo "capture OK"

echo "--- phase 3: tile-grid analysis (late-change + bounding boxes) ---"
ANALYSIS_LOG="$LOGDIR/analysis-v3-244.log"
rm -f "$ANALYSIS_LOG" "$ANALYSIS_LOG.done"
{
	echo "=== CONTROL (2.44.4 reference, 5ec7f0e) ==="
	control_dirs=$(ls -d "$BURST/data-v3-244"/control-*/ 2>/dev/null | sort -V)
	python3 "$BURST/analyze_burst_v3.py" control-244 $control_dirs
} > "$ANALYSIS_LOG" 2>&1
touch "$ANALYSIS_LOG.done"

echo ORCHESTRATE_244_DONE
