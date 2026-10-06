#!/bin/bash
# orchestrate-v3-retry.sh -- retries V3 (2.44.4/5ec7f0e render-check validation) after S4, so
# S4 gets first claim on tonight's live-card window. Under the lock: OTA to 5ec7f0e
# (ota-verify-5ec7f0e.sh, which checks OTA_EXIT before rebooting), 5 render-check runs, then OTA
# back to d97d6fe so bench is left where S4 benchmarked it. Self .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-v3-retry.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
EVIDENCE=/home/tjwise/185-evidence/render-check-validation
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
RENDER_CHECK=/home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check.sh
S4_PID=1899388
mkdir -p "$EVIDENCE"

echo "--- waiting for orchestrate-s4-smoothness-soak (pid $S4_PID) to exit ---"
while kill -0 "$S4_PID" 2>/dev/null; do sleep 10; done
echo "S4 chain exited"

echo "--- OTA to 5ec7f0e (2.44.4), under lock ---"
OTA_LOG="$LOGDIR/ota-verify-5ec7f0e-retry.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-5ec7f0e.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: OTA to 5ec7f0e failed rc=$OTA_RC, see $OTA_LOG -- bench left as found, not retrying blind"
	exit 1
fi
echo "ota-verify OK, bench on 5ec7f0e"

echo "--- V3 retry: 5 render-check runs (under lock) ---"
(
	flock 9
	out="$EVIDENCE/V3-5ec7f0e-244.log"
	rm -f "$out"
	for i in 1 2 3 4 5; do
		echo "=== V3-retry run $i/5 $(date -u +%FT%TZ) ===" >> "$out"
		"$RENDER_CHECK" "$T" >> "$out" 2>&1
		rc=$?
		echo "V3-retry run $i rc=$rc" >> "$out"
	done
	echo "-- V3-retry rc tally: $(grep -o 'rc=[0-9]*' "$out" | sort | uniq -c | tr '\n' ' ')"
	echo "-- V3-retry stale tiles lines: $(grep 'stale tiles=' "$out" | tr '\n' ' ')"
) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo "--- OTA back to d97d6fe, under lock ---"
OTA_BACK_LOG="$LOGDIR/ota-verify-d97d6fe-back.log"
rm -f "$OTA_BACK_LOG" "$OTA_BACK_LOG.done"
flock "$LOCK" "$BURST/ota-verify-d97d6fe.sh" > "$OTA_BACK_LOG" 2>&1
OTA_BACK_RC=$?
touch "$OTA_BACK_LOG.done"
if [ $OTA_BACK_RC -ne 0 ]; then
	echo "ABORT: OTA back to d97d6fe failed rc=$OTA_BACK_RC, see $OTA_BACK_LOG -- bench left on 5ec7f0e"
	exit 1
fi
echo "bench left on d97d6fe"

echo ORCHESTRATE_V3_RETRY_DONE
