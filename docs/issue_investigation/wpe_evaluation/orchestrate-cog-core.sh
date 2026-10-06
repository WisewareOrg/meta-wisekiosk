#!/bin/bash
# orchestrate-cog-core.sh -- queued behind orchestrate-stale-diag (waits on its pid, never
# edits it). Verifies bench buildinfo == d97d6fe (stop and report, no OTA, if it's anything
# else -- never capture a core against the wrong image). Runs capture-cog-core.sh from the
# -impl worktree (origin/185-wpe-evaluation, contains 2104998) with BENCH set, then
# analyze-cog-core.sh on the host against -185's own build/tmp-raspberrypi0-wifi (the worktree
# that actually built d97d6fe). Confirms core_pattern restored and /data/cog-core gone. Self
# .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-cog-core.log.done"' EXIT
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
D=/home/tjwise/meta-wisekiosk-185-impl/docs/issue_investigation/wpe_evaluation
TMPDIR_BUILD=/home/tjwise/meta-wisekiosk-185/build/tmp-raspberrypi0-wifi
EVIDENCE=/home/tjwise/185-evidence/cog-core
STALE_DIAG_PID=2884923

echo "--- waiting for orchestrate-stale-diag (pid $STALE_DIAG_PID) to exit ---"
while kill -0 "$STALE_DIAG_PID" 2>/dev/null; do sleep 15; done
echo "orchestrate-stale-diag exited"

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

echo "--- capture-cog-core.sh (under lock) ---"
if [ -e "$EVIDENCE" ]; then
	echo "ABORT: $EVIDENCE already exists -- not deleting it blindly; move it aside and rerun if that's expected"
	exit 1
fi
export BENCH="$T"
flock "$LOCK" "$D/capture-cog-core.sh" "$EVIDENCE"
CAP_RC=$?
echo "capture-cog-core.sh rc=$CAP_RC"
if [ $CAP_RC -ne 0 ]; then
	echo "ABORT: capture failed rc=$CAP_RC, see $EVIDENCE/"
	exit 1
fi

echo "--- analyze-cog-core.sh (host, no lock) ---"
"$D/analyze-cog-core.sh" "$EVIDENCE" "$TMPDIR_BUILD"
ANALYZE_RC=$?
echo "analyze-cog-core.sh rc=$ANALYZE_RC"

echo "--- confirm core_pattern restored and /data/cog-core gone ---"
"$KSSH" "$T" 'echo "core_pattern: $(cat /proc/sys/kernel/core_pattern)"; [ -e /data/cog-core ] && echo "COG_CORE_STILL_PRESENT" || echo "COG_CORE_GONE"'

echo "--- backtrace.txt (faulting thread) ---"
cat "$EVIDENCE/backtrace.txt" 2>&1

echo ORCHESTRATE_COG_CORE_DONE
