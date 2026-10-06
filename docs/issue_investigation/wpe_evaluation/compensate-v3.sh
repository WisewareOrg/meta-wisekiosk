#!/bin/bash
# compensate-v3.sh -- orchestrate-render-check.sh (pid 1878365) is running the pre-fix
# run_series (inode already open when the bug was fixed on disk), so its V3 phase will fail the
# same "label: unbound variable" way V1/V2 did, leaving no V3 runs. Waits for it to exit, checks
# whether V3's log is actually empty, and if so runs V3's 5 render-check series itself using the
# now-fixed logic, directly (bench should already be on 5ec7f0e from the OTA, which does not
# depend on run_series and already succeeded independently). Self .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/compensate-v3.log.done"' EXIT
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
EVIDENCE=/home/tjwise/185-evidence/render-check-validation
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
RENDER_CHECK=/home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check.sh
RENDER_CHECK_PID=1878365

echo "--- waiting for orchestrate-render-check (pid $RENDER_CHECK_PID) to exit ---"
while kill -0 "$RENDER_CHECK_PID" 2>/dev/null; do sleep 10; done
echo "render-check V1-V3 chain exited"

V3_LOG="$EVIDENCE/V3-5ec7f0e-244.log"
if [ -s "$V3_LOG" ] && grep -q 'rc=' "$V3_LOG"; then
	echo "V3_ALREADY_HAS_RUNS -- no compensation needed"
	exit 0
fi
echo "V3 log missing or empty ($V3_LOG) -- compensating"

echo "--- verify bench is on 5ec7f0e before compensating ---"
ACTUAL=$("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')
echo "buildinfo: $ACTUAL"
case "$ACTUAL" in
*"5ec7f0e"*) echo "BUILDINFO_MATCH" ;;
*) echo "ABORT: bench is not on 5ec7f0e, not compensating blind"; exit 1 ;;
esac

echo "--- V3 compensation: 5 render-check runs (under lock) ---"
(
	flock 9
	rm -f "$V3_LOG"
	for i in 1 2 3 4 5; do
		echo "=== V3 run $i/5 $(date -u +%FT%TZ) ===" >> "$V3_LOG"
		"$RENDER_CHECK" "$T" >> "$V3_LOG" 2>&1
		rc=$?
		echo "V3 run $i rc=$rc" >> "$V3_LOG"
	done
	echo "-- V3 rc tally: $(grep -o 'rc=[0-9]*' "$V3_LOG" | sort | uniq -c | tr '\n' ' ')"
	echo "-- V3 stale tiles lines: $(grep 'stale tiles=' "$V3_LOG" | tr '\n' ' ')"
) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo COMPENSATE_V3_DONE
