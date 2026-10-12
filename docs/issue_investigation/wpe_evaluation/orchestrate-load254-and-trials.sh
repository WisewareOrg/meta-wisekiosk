#!/bin/bash
# orchestrate-load254-and-trials.sh -- waits for run-load-experiment.sh (254) to exit by pid,
# runs its per-phase analysis (no lock needed, local files only), then under the lock: cog
# feature discovery, and one fix trial per damage/compositing-related feature (damage-propagation
# / damage-for-compositing names first), then one trial with all of them disabled together. Self
# .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-load254-and-trials.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
LOAD_PID=1732581

echo "--- waiting for run-load-experiment.sh (pid $LOAD_PID) to exit ---"
while kill -0 "$LOAD_PID" 2>/dev/null; do sleep 5; done
echo "load experiment process exited"

if ! grep -q "LOAD_EXPERIMENT_DONE" "$LOGDIR/load-254.log"; then
	echo "ABORT: load-254.log did not reach its end marker, see $LOGDIR/load-254.log"
	exit 1
fi
echo "load-254 capture OK"

echo "--- 254 load analysis, per phase (local files only, no lock needed) ---"
ANALYSIS_LOG="$LOGDIR/analysis-load-254.log"
rm -f "$ANALYSIS_LOG" "$ANALYSIS_LOG.done"
{
	for phase in idle spinner drmloop; do
		echo "=== 254 / $phase ==="
		dirs=$(ls -d "$BURST/data-load-254"/"$phase"-*/ 2>/dev/null | sort -V)
		python3 "$BURST/analyze_fw_burst.py" "254-$phase" fw $dirs
		echo
	done
} > "$ANALYSIS_LOG" 2>&1
touch "$ANALYSIS_LOG.done"
echo "254 load analysis OK"

echo "--- feature discovery (under lock) ---"
FEAT_LOG="$LOGDIR/cog-features-help.log"
rm -f "$FEAT_LOG"
flock "$LOCK" /home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh "$T" 'cog --features=help' > "$FEAT_LOG" 2>&1
echo "full --features=help saved to $FEAT_LOG"

CANDIDATES=$(grep -iE 'Damag|Partial|BufferAge|Compositing' "$FEAT_LOG" | awk '{print $1}' | sort -u)
echo "candidate lines:"
grep -iE 'Damag|Partial|BufferAge|Compositing' "$FEAT_LOG"
echo "candidate names: $CANDIDATES"

if [ -z "$CANDIDATES" ]; then
	echo "ABORT: no Damage/Partial/BufferAge/Compositing feature names found in --features=help"
	exit 1
fi

PRIORITY=$(printf '%s\n' "$CANDIDATES" | grep -iE 'Damag.*Composit|Composit.*Damag|Propagat.*Damag|Damag.*Propagat' || true)
REST=$(printf '%s\n' "$CANDIDATES" | { [ -n "$PRIORITY" ] && grep -vxF -f <(printf '%s\n' "$PRIORITY") || cat; })
ORDER=$(printf '%s\n%s\n' "$PRIORITY" "$REST" | grep -v '^$')
echo "trial order: $ORDER"

echo "--- fix trials, one per candidate (under lock) ---"
TRIAL_LOG="$LOGDIR/fix-trials.log"
rm -f "$TRIAL_LOG" "$TRIAL_LOG.done"
: > "$TRIAL_LOG"
ALL_NAMES=""
for name in $ORDER; do
	echo "=== trial: -$name ===" | tee -a "$TRIAL_LOG"
	flock "$LOCK" "$BURST/run-feature-trial.sh" "$T" "-$name" "$BURST/trial-$name" >> "$TRIAL_LOG" 2>&1
	rc=$?
	echo "trial -$name rc=$rc" | tee -a "$TRIAL_LOG"
	ALL_NAMES="$ALL_NAMES,-$name"
done

ALL_NAMES=${ALL_NAMES#,}
if [ -n "$ALL_NAMES" ]; then
	echo "=== trial: all together ($ALL_NAMES) ===" | tee -a "$TRIAL_LOG"
	flock "$LOCK" "$BURST/run-feature-trial.sh" "$T" "$ALL_NAMES" "$BURST/trial-all" >> "$TRIAL_LOG" 2>&1
	rc=$?
	echo "trial all rc=$rc" | tee -a "$TRIAL_LOG"
fi
touch "$TRIAL_LOG.done"

echo ORCHESTRATE_LOAD254_AND_TRIALS_DONE
