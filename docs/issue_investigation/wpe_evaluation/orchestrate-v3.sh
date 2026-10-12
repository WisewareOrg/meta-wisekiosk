#!/bin/bash
# orchestrate-v3.sh -- bench is already on 449e571 (confirmed before launch, no build/OTA phase
# needed): runs the burst-v3 capture (under the lock), then the tile-grid disagreement analysis.
# Each phase gets its own LOG/.done pair so progress is visible without watching this script run.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
# Self .done: EVERY orchestrator writes its own top-level .log.done as its last act,
# in an EXIT trap so it fires on an early abort too -- a waiter blocks on this file,
# not on an outer wrapper that may not exist.
trap 'touch "$LOGDIR/orchestrate-v3.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock

echo "--- phase 1: burst v3 capture (under lock, ~24 min: 12 min control + 12 min CPU) ---"
BURST_LOG="$LOGDIR/burst-v3.log"
rm -f "$BURST_LOG" "$BURST_LOG.done"
flock -n "$LOCK" "$BURST/run-burst-capture-v3.sh" "${BENCH:?ssh target}" "$BURST/data-v3" > "$BURST_LOG" 2>&1
BURST_RC=$?
touch "$BURST_LOG.done"
if [ $BURST_RC -ne 0 ]; then
	echo "ABORT: burst capture failed rc=$BURST_RC, see $BURST_LOG"
	exit 1
fi
if ! grep -q "BURST_CAPTURE_V3_DONE" "$BURST_LOG"; then
	echo "ABORT: burst capture did not reach its end marker, see $BURST_LOG"
	exit 1
fi
echo "burst capture OK"

echo "--- phase 2: tile-grid analysis ---"
ANALYSIS_LOG="$LOGDIR/analysis-v3.log"
rm -f "$ANALYSIS_LOG" "$ANALYSIS_LOG.done"
{
	echo "=== CONTROL ==="
	control_dirs=$(ls -d "$BURST/data-v3"/control-*/ 2>/dev/null | sort -V)
	python3 "$BURST/analyze_burst_v3.py" control $control_dirs
	echo
	echo "=== CPU RENDERING ==="
	cpu_dirs=$(ls -d "$BURST/data-v3"/cpu-*/ 2>/dev/null | sort -V)
	python3 "$BURST/analyze_burst_v3.py" cpu $cpu_dirs
} > "$ANALYSIS_LOG" 2>&1
touch "$ANALYSIS_LOG.done"

echo ORCHESTRATE_V3_DONE
