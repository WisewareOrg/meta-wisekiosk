#!/bin/bash
# orchestrate-trials.sh -- the explicit B/T trial sequence (names taken verbatim from
# cog-features-help.log, no parsing), each under the lock: KIOSK_COG_FEATURES -> restart ->
# settle (up to 20 min) -> 6 v3 bursts + one 90-frame fwgrab burst -> both analyses -> restore.
# Self .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-trials.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}

# name:features-value pairs, in the exact required order.
TRIALS=(
	"B0:UNSET"
	"T1:-UseDamagingInformationForCompositing"
	"T2:-PropagateDamagingInformation"
	"T3:-UnifyDamagedRegions"
	"B1:UNSET"
	"T4:-UseDamagingInformationForCompositing,-PropagateDamagingInformation,-UnifyDamagedRegions"
	"T5:-UseSkiaForComposition"
	"B2:UNSET"
)

TRIAL_LOG="$LOGDIR/fix-trials.log"
rm -f "$TRIAL_LOG" "$TRIAL_LOG.done"
: > "$TRIAL_LOG"

for entry in "${TRIALS[@]}"; do
	name=${entry%%:*}
	features=${entry#*:}
	echo "=== $name: KIOSK_COG_FEATURES=$features ===" | tee -a "$TRIAL_LOG"
	flock "$LOCK" "$BURST/run-feature-trial.sh" "$T" "$features" "$BURST/trial-$name" >> "$TRIAL_LOG" 2>&1
	rc=$?
	echo "$name rc=$rc" | tee -a "$TRIAL_LOG"
done
touch "$TRIAL_LOG.done"

echo ORCHESTRATE_TRIALS_DONE
