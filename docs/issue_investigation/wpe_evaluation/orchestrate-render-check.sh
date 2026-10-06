#!/bin/bash
# orchestrate-render-check.sh -- proof of the new render-check STALE verdict (185-wpe-evaluation
# 51944db, the -impl worktree; HEAD verified to match before running). Waits for the trial-rerun
# chain to exit, then under the lock: V1 (138d914 default, 5 runs), V2 (138d914 with
# KIOSK_COG_FEATURES=-UseDamagingInformationForCompositing, backed up/restored/cmp-verified, 5
# runs), V3 (OTA to 5ec7f0e/2.44.4, 5 runs). Bench is left on 5ec7f0e afterward. Self .done in an
# EXIT trap. Output goes under /home/tjwise/185-evidence/, never /tmp.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-render-check.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
EVIDENCE=/home/tjwise/185-evidence/render-check-validation
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
RENDER_CHECK=/home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check.sh
RERUN_PID=1742818
mkdir -p "$EVIDENCE"
export T KSSH RENDER_CHECK EVIDENCE LOGDIR

echo "--- verify -impl worktree HEAD is 51944db ---"
cd /home/tjwise/meta-wisekiosk-185-impl
HEAD_SHA=$(git rev-parse HEAD)
echo "HEAD=$HEAD_SHA"
case "$HEAD_SHA" in
51944db*) echo "HEAD_MATCH" ;;
*) echo "ABORT: -impl worktree HEAD is not 51944db"; exit 1 ;;
esac

echo "--- waiting for orchestrate-trials-rerun (pid $RERUN_PID) to exit ---"
while kill -0 "$RERUN_PID" 2>/dev/null; do sleep 10; done
echo "rerun chain exited"

# run_series <label> <n> -- n render-check runs against bench, rc + stale-tiles line each,
# appended to a per-phase log under EVIDENCE.
run_series() {
	local label=$1
	local n=$2
	local out="$EVIDENCE/$label.log"
	rm -f "$out"
	for i in $(seq 1 "$n"); do
		echo "=== $label run $i/$n $(date -u +%FT%TZ) ===" >> "$out"
		"$RENDER_CHECK" "$T" >> "$out" 2>&1
		rc=$?
		echo "$label run $i rc=$rc" >> "$out"
	done
	echo "-- $label rc tally: $(grep -o 'rc=[0-9]*' "$out" | sort | uniq -c | tr '\n' ' ')"
	echo "-- $label stale tiles lines: $(grep 'stale tiles=' "$out" | tr '\n' ' ')"
}

echo "--- V1: 138d914, default ---"
echo "buildinfo: $("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')"
echo "kiosk.conf: $("$KSSH" "$T" 'cat /data/config/kiosk.conf')"
( flock 9; run_series V1-138d914-default 5 ) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo "--- V2: 138d914, KIOSK_COG_FEATURES=-UseDamagingInformationForCompositing (under lock) ---"
V2_BACKUP="$EVIDENCE/kiosk.conf.v2-orig"
(
	flock 9
	# The restore must be a trap, installed BEFORE the edit, in THIS subshell: a bare sequence
	# of "do the work, then restore" skips the restore entirely if anything between backup and
	# restore dies -- including a set -u abort on an unbound variable, which is fatal and does
	# not fall through to the next command the way a plain nonzero exit would.
	restore_v2() {
		"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$V2_BACKUP"
		"$KSSH" "$T" 'systemctl restart kiosk'
		"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "${V2_BACKUP}.after"
		cmp "$V2_BACKUP" "${V2_BACKUP}.after" && echo "V2_RESTORE_IDENTICAL" || echo "V2_RESTORE_MISMATCH"
	}
	"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$V2_BACKUP"
	trap restore_v2 EXIT
	"$KSSH" "$T" "sh -s" <<'REMOTE'
C=/data/config/kiosk.conf
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_COG_FEATURES=-UseDamagingInformationForCompositing' >> $C
systemctl restart kiosk
REMOTE
	sleep 15
	run_series V2-138d914-nodamage 5
) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"
sleep 15

echo "--- V3: OTA to 5ec7f0e (2.44.4), under lock ---"
OTA_LOG="$LOGDIR/ota-verify-5ec7f0e-3.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-5ec7f0e.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: ota-verify to 5ec7f0e failed rc=$OTA_RC, see $OTA_LOG"
	exit 1
fi
echo "ota-verify OK, bench on 5ec7f0e"

( flock 9; run_series V3-5ec7f0e-244 5 ) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo "--- leaving bench on 5ec7f0e ---"
echo ORCHESTRATE_RENDER_CHECK_DONE
