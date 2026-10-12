#!/bin/bash
# orchestrate-trials-rerun.sh -- reruns T1, T2, T3 in full after a host /tmp-full corrupted
# T2's fw burst and T3's v3 bursts 3-4. Waits for the original trial chain (pid 1735756) to
# exit, then runs each under the lock, writing captures directly under
# /home/tjwise/185-evidence/burst/ (real disk, not /tmp) via run-feature-trial.sh (which now
# checks free space before every burst and aborts cleanly under 1G). Self .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-trials-rerun.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
EVIDENCE=/home/tjwise/185-evidence/burst
T=${BENCH:?ssh target, e.g. root@<bench>}
ORIG_PID=1735756

echo "--- waiting for the original trial chain (pid $ORIG_PID) to exit ---"
while kill -0 "$ORIG_PID" 2>/dev/null; do sleep 10; done
echo "original chain process exited"

RERUNS=(
	"T1:-UseDamagingInformationForCompositing"
	"T2:-PropagateDamagingInformation"
	"T3:-UnifyDamagedRegions"
)

RERUN_LOG="$LOGDIR/fix-trials-rerun.log"
rm -f "$RERUN_LOG" "$RERUN_LOG.done"
: > "$RERUN_LOG"

for entry in "${RERUNS[@]}"; do
	name=${entry%%:*}
	features=${entry#*:}
	echo "=== ${name}-rerun: KIOSK_COG_FEATURES=$features ===" | tee -a "$RERUN_LOG"
	flock "$LOCK" "$BURST/run-feature-trial.sh" "$T" "$features" "$EVIDENCE/trial-${name}-rerun" >> "$RERUN_LOG" 2>&1
	rc=$?
	echo "${name}-rerun rc=$rc" | tee -a "$RERUN_LOG"
done
touch "$RERUN_LOG.done"

echo ORCHESTRATE_TRIALS_RERUN_DONE
