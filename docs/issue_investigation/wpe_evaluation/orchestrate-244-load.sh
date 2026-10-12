#!/bin/bash
# orchestrate-244-load.sh -- appends the 3-phase CPU-load experiment to the 2.44.4 (5ec7f0e)
# reference run, after its v3 control capture. Waits for orchestrate-244.log.done (the earlier
# chain), confirms it reached ORCHESTRATE_244_DONE (not an abort), then runs the load experiment
# under the lock -- no OTA here, bench is already on 5ec7f0e from that chain -- then analyses
# each phase. Self .done in an EXIT trap from the start.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-244-load.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
IMG=244

echo "--- waiting for orchestrate-244.log.done ---"
until [ -f "$LOGDIR/orchestrate-244.log.done" ]; do sleep 10; done
if ! grep -q "ORCHESTRATE_244_DONE" "$LOGDIR/orchestrate-244.log"; then
	echo "ABORT: 2.44 reference chain did not complete cleanly, see $LOGDIR/orchestrate-244.log"
	exit 1
fi
echo "2.44 chain OK, bench is on 5ec7f0e"

echo "--- confirm buildinfo still 5ec7f0e before the load experiment ---"
ACTUAL=$(/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')
echo "buildinfo: $ACTUAL"
case "$ACTUAL" in
*"5ec7f0e"*) echo "BUILDINFO_MATCH" ;;
*) echo "ABORT: expected 5ec7f0e"; exit 1 ;;
esac

echo "--- load experiment (under lock) ---"
LOAD_LOG="$LOGDIR/load-$IMG.log"
rm -f "$LOAD_LOG" "$LOAD_LOG.done"
flock "$LOCK" "$BURST/run-load-experiment.sh" "$T" "$BURST/data-load-$IMG" "$IMG" > "$LOAD_LOG" 2>&1
LOAD_RC=$?
touch "$LOAD_LOG.done"
if [ $LOAD_RC -ne 0 ]; then
	echo "ABORT: load experiment failed rc=$LOAD_RC, see $LOAD_LOG"
	exit 1
fi
if ! grep -q "LOAD_EXPERIMENT_DONE" "$LOAD_LOG"; then
	echo "ABORT: load experiment did not reach its end marker, see $LOAD_LOG"
	exit 1
fi
echo "load experiment OK"

echo "--- analysis, per phase ---"
ANALYSIS_LOG="$LOGDIR/analysis-load-$IMG.log"
rm -f "$ANALYSIS_LOG" "$ANALYSIS_LOG.done"
{
	for phase in idle spinner drmloop; do
		echo "=== $IMG / $phase ==="
		dirs=$(ls -d "$BURST/data-load-$IMG"/"$phase"-*/ 2>/dev/null | sort -V)
		python3 "$BURST/analyze_fw_burst.py" "$IMG-$phase" fw $dirs
		echo
	done
} > "$ANALYSIS_LOG" 2>&1
touch "$ANALYSIS_LOG.done"

echo ORCHESTRATE_244_LOAD_DONE
