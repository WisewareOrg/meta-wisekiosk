#!/bin/bash
# orchestrate-cog-core2.sh -- retry of orchestrate-cog-core.sh, which aborted because
# capture-cog-core.sh lacked +x (rc 69, permission denied; the aborted run never armed
# core_pattern or wrote /data/cog-core -- confirmed before this was written). Invokes both
# capture-cog-core.sh and analyze-cog-core.sh as `bash <script>`, so a missing execute bit
# can't block it again. Queued behind orchestrate-ab (waits on its pid, never edits it).
# Repeats the buildinfo == d97d6fe check (stop and report, no OTA, if it's anything else).
# Self .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-cog-core2.log.done"' EXIT
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
D=/home/tjwise/meta-wisekiosk-185-impl/docs/issue_investigation/wpe_evaluation
TMPDIR_BUILD=/home/tjwise/meta-wisekiosk-185/build/tmp-raspberrypi0-wifi
EVIDENCE=/home/tjwise/185-evidence/cog-core
AB_PID=2910190

echo "--- waiting for orchestrate-ab (pid $AB_PID) to exit ---"
while kill -0 "$AB_PID" 2>/dev/null; do sleep 15; done
echo "orchestrate-ab exited"

echo "--- verify -impl worktree HEAD contains 2104998 ---"
cd /home/tjwise/meta-wisekiosk-185-impl
HEAD_SHA=$(git rev-parse HEAD)
echo "HEAD=$HEAD_SHA"
git merge-base --is-ancestor 2104998 HEAD || { echo "ABORT: HEAD does not contain 2104998"; exit 1; }
echo "HEAD_CONTAINS_2104998"

echo "--- verify bench buildinfo == d97d6fe ---"
ACTUAL=$("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')
echo "buildinfo: $ACTUAL"
case "$ACTUAL" in
*d97d6fe*) echo "BUILDINFO_MATCH" ;;
*)
	echo "STOP: bench is not on d97d6fe (buildinfo: $ACTUAL) -- not capturing against the wrong image"
	exit 1
	;;
esac

echo "--- pre-check: core_pattern original, /data/cog-core absent ---"
"$KSSH" "$T" 'echo "core_pattern: $(cat /proc/sys/kernel/core_pattern)"; [ -e /data/cog-core ] && echo "COG_CORE_EXISTS" || echo "COG_CORE_ABSENT"'

echo "--- capture-cog-core.sh (via bash, under lock) ---"
if [ -e "$EVIDENCE" ]; then
	echo "ABORT: $EVIDENCE already exists -- not deleting it blindly; move it aside and rerun if that's expected"
	exit 1
fi
export BENCH="$T"
flock "$LOCK" bash "$D/capture-cog-core.sh" "$EVIDENCE"
CAP_RC=$?
echo "capture-cog-core.sh rc=$CAP_RC"
if [ $CAP_RC -ne 0 ]; then
	echo "ABORT: capture failed rc=$CAP_RC, see $EVIDENCE/"
	exit 1
fi

echo "--- analyze-cog-core.sh (via bash, host, no lock) ---"
bash "$D/analyze-cog-core.sh" "$EVIDENCE" "$TMPDIR_BUILD"
ANALYZE_RC=$?
echo "analyze-cog-core.sh rc=$ANALYZE_RC"

echo "--- confirm core_pattern restored and /data/cog-core gone ---"
"$KSSH" "$T" 'echo "core_pattern: $(cat /proc/sys/kernel/core_pattern)"; [ -e /data/cog-core ] && echo "COG_CORE_STILL_PRESENT" || echo "COG_CORE_GONE"'

echo "--- backtrace.txt (faulting thread) ---"
cat "$EVIDENCE/backtrace.txt" 2>&1

echo ORCHESTRATE_COG_CORE2_DONE
