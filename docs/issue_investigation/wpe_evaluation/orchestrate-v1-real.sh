#!/bin/bash
# orchestrate-v1-real.sh -- the real test the owner wants instead of the suspect KIOSK_COG_
# FEATURES override: OTA to the actual pre-fix 138d914 image (built in the dedicated -254
# worktree, never touching the d97d6fe worktree), run the 646c513+ render-check helper for real,
# then OTA back to d97d6fe (whose build/deploy was never touched, so no rebuild needed there).
# Self .done in an EXIT trap. Output under /home/tjwise/185-evidence/, never /tmp.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-v1-real.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
EVIDENCE=/home/tjwise/185-evidence/render-check-validation
T=${BENCH:?ssh target, e.g. root@<bench>}
RENDER_CHECK=/home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check.sh
BUILD_LOG="$LOGDIR/build-138d914-tonight.log"
mkdir -p "$EVIDENCE"

echo "--- verify -impl worktree HEAD contains 646c513 ---"
cd /home/tjwise/meta-wisekiosk-185-impl
HEAD_SHA=$(git rev-parse HEAD)
echo "HEAD=$HEAD_SHA"
git merge-base --is-ancestor 646c513 HEAD || { echo "ABORT: HEAD does not contain 646c513"; exit 1; }
echo "HEAD_CONTAINS_646c513"

echo "--- waiting for the 138d914 build (triggered after smoothness) ---"
until [ -f "$BUILD_LOG.done" ]; do sleep 10; done
if ! grep -q "BUILD_EXIT=0" "$BUILD_LOG"; then
	echo "ABORT: 138d914 build did not succeed, see $BUILD_LOG"
	exit 1
fi
echo "build OK"

echo "--- OTA to 138d914 (under lock) ---"
OTA_LOG="$LOGDIR/ota-verify-138d914-tonight.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-138d914.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: OTA to 138d914 failed rc=$OTA_RC, see $OTA_LOG -- not touching the device further"
	exit 1
fi
echo "ota-verify OK, bench on 138d914"

echo "--- V1-real: 5 render-check runs + 1 v3 burst (under lock) ---"
(
	flock 9
	out="$EVIDENCE/V1-real-138d914.log"
	rm -f "$out"
	for i in 1 2 3 4 5; do
		echo "=== V1-real run $i/5 $(date -u +%FT%TZ) ===" >> "$out"
		"$RENDER_CHECK" "$T" >> "$out" 2>&1
		rc=$?
		echo "V1-real run $i rc=$rc" >> "$out"
	done
	echo "-- V1-real rc tally: $(grep -o 'rc=[0-9]*' "$out" | sort | uniq -c | tr '\n' ' ')"
	echo "-- V1-real stale tiles lines: $(grep 'stale tiles=' "$out" | tr '\n' ' ')"

	echo "-- V1-real independent check: 1 v3-style burst + analysis --"
	"$BURST/run-v3-short.sh" "$T" "$EVIDENCE/V1-real-v3burst" 1
	dirs=$(ls -d "$EVIDENCE/V1-real-v3burst"/control-*/ 2>/dev/null | sort -V)
	python3 "$BURST/analyze_burst_v3.py" V1real $dirs
) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo "--- OTA back to d97d6fe (under lock, build/deploy untouched, no rebuild needed) ---"
OTA_BACK_LOG="$LOGDIR/ota-verify-d97d6fe-back3.log"
rm -f "$OTA_BACK_LOG" "$OTA_BACK_LOG.done"
flock "$LOCK" "$BURST/ota-verify-d97d6fe.sh" > "$OTA_BACK_LOG" 2>&1
OTA_BACK_RC=$?
touch "$OTA_BACK_LOG.done"
if [ $OTA_BACK_RC -ne 0 ]; then
	echo "ABORT: OTA back to d97d6fe failed rc=$OTA_BACK_RC, see $OTA_BACK_LOG -- bench left on 138d914"
	exit 1
fi
echo "bench back on d97d6fe"

echo "--- final kiosk.conf check ---"
echo "kiosk.conf: $(/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh "$T" 'cat /data/config/kiosk.conf')"

echo ORCHESTRATE_V1_REAL_DONE
