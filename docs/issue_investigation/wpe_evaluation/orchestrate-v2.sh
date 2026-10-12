#!/bin/bash
# orchestrate-v2.sh -- waits for the already-launched 449e571 build, then runs OTA+verify (under
# the lock), then the burst-v2 capture + analysis (under the lock). Each phase gets its own
# LOG/.done pair so progress is visible without anyone needing to watch this script run.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock

echo "--- waiting for build-449e571.log.done ---"
until [ -f "$LOGDIR/build-449e571.log.done" ]; do sleep 10; done
if ! grep -q "BUILD_EXIT=0" "$LOGDIR/build-449e571.log"; then
	echo "ABORT: build did not succeed, see $LOGDIR/build-449e571.log"
	exit 1
fi
echo "build OK"

echo "--- phase 2: OTA + verify (under lock) ---"
OTA_LOG="$LOGDIR/ota-verify-449e571.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock -n "$LOCK" "$BURST/ota-verify-449e571.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: ota-verify failed rc=$OTA_RC, see $OTA_LOG"
	exit 1
fi
echo "ota-verify OK"

echo "--- phase 3: burst v2 capture (under lock) ---"
BURST_LOG="$LOGDIR/burst-v2.log"
rm -f "$BURST_LOG" "$BURST_LOG.done"
flock -n "$LOCK" "$BURST/run-burst-capture-v2.sh" "${BENCH:?ssh target}" "$BURST/data-v2" > "$BURST_LOG" 2>&1
BURST_RC=$?
touch "$BURST_LOG.done"
if [ $BURST_RC -ne 0 ]; then
	echo "ABORT: burst capture failed rc=$BURST_RC, see $BURST_LOG"
	exit 1
fi
echo "burst capture OK"

echo "--- phase 4: analysis ---"
ANALYSIS_LOG="$LOGDIR/analysis-v2.log"
rm -f "$ANALYSIS_LOG" "$ANALYSIS_LOG.done"
{
	echo "=== CONTROL ==="
	python3 "$BURST/analyze_burst_v2.py" "$BURST/data-v2/control-1"
	echo
	echo "=== CPU RENDERING (2 batches combined) ==="
	python3 "$BURST/analyze_burst_v2.py" "$BURST/data-v2/cpu-1" "$BURST/data-v2/cpu-2"
} > "$ANALYSIS_LOG" 2>&1
touch "$ANALYSIS_LOG.done"

echo ORCHESTRATE_V2_DONE
