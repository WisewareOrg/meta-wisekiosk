#!/bin/bash
# orchestrate-stale-diag.sh -- 5x [render-check's own 30-capture series, kept, under lock] on
# 138d914, each immediately followed by one v3-style burst + analysis as the independent
# signal, so a disagreement between the live verdict and the burst (as pairs 2/3 showed this
# morning) can be examined frame-by-frame afterward. No cards gate -- the fault appeared with
# l=0 this morning -- but cards-probe.js is deployed once up front (KIOSK_PROBE=1, restore trap
# installed before the edit) purely to RECORD the CP state before each series, never to block
# on it. Confirms/OTAs to 138d914 first if the buildinfo check fails. Ends with an OTA back to
# d97d6fe (OTA_EXIT checked; one retry if the install fails, e.g. a network reset). Self .done
# in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-stale-diag.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
D=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation
EVIDENCE=/home/tjwise/185-evidence/stale-diag
AB_PID=2849015
mkdir -p "$EVIDENCE"

echo "--- waiting for orchestrate-ab (pid $AB_PID) to exit ---"
while kill -0 "$AB_PID" 2>/dev/null; do sleep 15; done
echo "orchestrate-ab exited"

echo "--- confirm bench is on 138d914; OTA only if not ---"
ACTUAL=$("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')
echo "buildinfo: $ACTUAL"
case "$ACTUAL" in
*138d914*) echo "ALREADY_ON_138D914" ;;
*)
	echo "not on 138d914 -- OTA'ing (under lock)"
	OTA_LOG="$LOGDIR/ota-verify-138d914-stalediag.log"
	rm -f "$OTA_LOG" "$OTA_LOG.done"
	flock "$LOCK" "$BURST/ota-verify-138d914.sh" > "$OTA_LOG" 2>&1
	OTA_RC=$?
	touch "$OTA_LOG.done"
	[ $OTA_RC -eq 0 ] || { echo "ABORT: OTA to 138d914 failed rc=$OTA_RC, see $OTA_LOG"; exit 1; }
	echo "ota-verify OK"
	;;
esac

echo "--- deploy cards-probe.js once, for recording only (no gate) ---"
CP_BACKUP="$EVIDENCE/kiosk.conf.orig"
RESTORE_PENDING=0
restore_cp() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$CP_BACKUP"
	"$KSSH" "$T" 'rm -f /home/root/kiosk-probe.js; systemctl restart kiosk'
	AFTER="${CP_BACKUP}.after"
	"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$AFTER"
	cmp "$CP_BACKUP" "$AFTER" && echo "STALEDIAG_RESTORE_IDENTICAL" || echo "STALEDIAG_RESTORE_MISMATCH"
}
trap 'restore_cp; touch "$LOGDIR/orchestrate-stale-diag.log.done"' EXIT
(
	flock 9
	"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$CP_BACKUP"
	RESTORE_PENDING=1
	"$KSSH" "$T" 'cat > /home/root/kiosk-probe.js' < "$D/cards-probe.js"
	DEPLOY_OUT=$("$KSSH" "$T" "sh -s" <<'REMOTE'
C=/data/config/kiosk.conf
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_PROBE=1' >> $C
systemctl restart kiosk
echo "start-epoch $(date +%s)"
REMOTE
)
	printf '%s\n' "$DEPLOY_OUT"
	echo "$DEPLOY_OUT" | sed -n 's/^start-epoch \([0-9]*\)$/\1/p' > "$EVIDENCE/.start-epoch"
) 9>"$LOCK"
RESTORE_PENDING=1
START=$(cat "$EVIDENCE/.start-epoch" 2>/dev/null)
sleep 20

for n in 1 2 3 4 5; do
	CP_STATE=$("$KSSH" "$T" "journalctl -u kiosk --since @${START:-0} -o cat --no-pager | grep 'CP|' | tail -1" 2>/dev/null)
	echo "series $n CP state: ${CP_STATE:-<none read>}"

	sdir="$EVIDENCE/series$n"
	echo "=== series $n/5 starting $(date -u +%FT%TZ) ==="
	flock "$LOCK" "$BURST/run-stale-diag-series.sh" "$T" "$sdir"
	rc=$?
	echo "=== series $n exit=$rc done $(date -u +%FT%TZ) ==="

	echo "--- series $n: 1 v3-style burst + analysis ---"
	bdir="$EVIDENCE/series$n-v3burst"
	flock "$LOCK" "$BURST/run-v3-short.sh" "$T" "$bdir" 1
	dirs=$(ls -d "$bdir"/control-*/ 2>/dev/null | sort -V)
	python3 "$BURST/analyze_burst_v3.py" "series$n" $dirs
done

echo "--- summary: series verdicts and burst disagreement counts, in run order (series 1-5) ---"
grep -E "^series [0-9] CP state:|^=== series [0-9]/5 starting|STALE:|no stale region|stale-check rc=|disagreeing_excl_late_change=" \
	"$LOGDIR/orchestrate-stale-diag.log" 2>/dev/null

restore_cp
RESTORE_PENDING=0

echo "--- OTA back to d97d6fe (OTA_EXIT checked, one retry on failure) ---"
OTA_BACK_LOG="$LOGDIR/ota-verify-d97d6fe-stalediag-back.log"
for attempt in 1 2; do
	rm -f "$OTA_BACK_LOG" "$OTA_BACK_LOG.done"
	flock "$LOCK" "$BURST/ota-verify-d97d6fe.sh" > "$OTA_BACK_LOG" 2>&1
	OTA_BACK_RC=$?
	touch "$OTA_BACK_LOG.done"
	if [ $OTA_BACK_RC -eq 0 ]; then
		echo "bench back on d97d6fe (attempt $attempt)"
		break
	fi
	echo "OTA back to d97d6fe failed rc=$OTA_BACK_RC on attempt $attempt, see $OTA_BACK_LOG"
	if [ "$attempt" = 2 ]; then
		echo "ABORT: OTA back to d97d6fe failed twice -- bench left on 138d914"
		exit 1
	fi
	echo "retrying once"
done

echo ORCHESTRATE_STALE_DIAG_DONE
