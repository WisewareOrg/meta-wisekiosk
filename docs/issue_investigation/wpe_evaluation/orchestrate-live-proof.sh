#!/bin/bash
# orchestrate-live-proof.sh -- live proof of the 646c513+ render-check helper, re-sequenced
# ahead of S4 since the cards gate is idling (closed-for-the-night, 3/4 live). One process,
# written fresh (no inter-process pid-chaining, so no inode-staleness risk): -impl HEAD checked
# to contain 646c513, OTA_EXIT checked on every OTA, every kiosk.conf edit's restore+cmp
# installed as an EXIT trap BEFORE the edit in the same shell.
#   a. V4b on d97d6fe: 5 runs, default. Expect rc 0.
#   b. V1b on d97d6fe: KIOSK_COG_FEATURES=UseDamagingInformationForCompositing, 5 runs, argv
#      logged. Expect mostly rc 3.
#   c. OTA 5ec7f0e (2.44.4): V3, 5 runs. Expect rc 0.
#   d. OTA back to d97d6fe, verify, kiosk.conf checked against known-good.
#   e. S4: cards-gated smoothness x3 (VOID reruns once) + soak.
# Self .done in an EXIT trap. Output under /home/tjwise/185-evidence/, never /tmp.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-live-proof.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
EVIDENCE=/home/tjwise/185-evidence/render-check-validation
D=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation
OUTDIR=/home/tjwise/185-evidence/s4
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
RENDER_CHECK=/home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check.sh
KNOWN_GOOD="KIOSK_INSPECTOR=0"
mkdir -p "$EVIDENCE" "$OUTDIR"

echo "--- verify -impl worktree HEAD contains 646c513 ---"
cd /home/tjwise/meta-wisekiosk-185-impl
HEAD_SHA=$(git rev-parse HEAD)
echo "HEAD=$HEAD_SHA"
git merge-base --is-ancestor 646c513 HEAD || { echo "ABORT: HEAD does not contain 646c513"; exit 1; }
echo "HEAD_CONTAINS_646c513"

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

echo "--- a. V4b: d97d6fe, default (under lock) ---"
echo "buildinfo: $("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')"
echo "kiosk.conf: $("$KSSH" "$T" 'cat /data/config/kiosk.conf')"
( flock 9; run_series V4b-d97d6fe-default 5 ) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo "--- b. V1b: d97d6fe, KIOSK_COG_FEATURES=UseDamagingInformationForCompositing (under lock) ---"
V1B_BACKUP="$EVIDENCE/kiosk.conf.v1b-orig"
(
	flock 9
	restore_v1b() {
		"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$V1B_BACKUP"
		"$KSSH" "$T" 'systemctl restart kiosk'
		"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "${V1B_BACKUP}.after"
		cmp "$V1B_BACKUP" "${V1B_BACKUP}.after" && echo "V1B_RESTORE_IDENTICAL" || echo "V1B_RESTORE_MISMATCH"
	}
	"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$V1B_BACKUP"
	trap restore_v1b EXIT
	"$KSSH" "$T" "sh -s" <<'REMOTE'
C=/data/config/kiosk.conf
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_COG_FEATURES=UseDamagingInformationForCompositing' >> $C
systemctl restart kiosk
REMOTE
	sleep 15
	argv=$("$KSSH" "$T" 'pid=$(pidof cog | cut -d" " -f1); [ -n "$pid" ] && tr "\0" " " < /proc/$pid/cmdline')
	echo "V1b cog argv=[$argv]"
	run_series V1b-d97d6fe-reenabled 5
) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo "--- c. OTA to 5ec7f0e (2.44.4), under lock ---"
OTA_LOG="$LOGDIR/ota-verify-5ec7f0e-live.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-5ec7f0e.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: OTA to 5ec7f0e failed rc=$OTA_RC, see $OTA_LOG"
	exit 1
fi
echo "ota-verify OK, bench on 5ec7f0e"
( flock 9; run_series V3-5ec7f0e-live 5 ) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo "--- d. OTA back to d97d6fe, under lock ---"
OTA_BACK_LOG="$LOGDIR/ota-verify-d97d6fe-back2.log"
rm -f "$OTA_BACK_LOG" "$OTA_BACK_LOG.done"
flock "$LOCK" "$BURST/ota-verify-d97d6fe.sh" > "$OTA_BACK_LOG" 2>&1
OTA_BACK_RC=$?
touch "$OTA_BACK_LOG.done"
if [ $OTA_BACK_RC -ne 0 ]; then
	echo "ABORT: OTA back to d97d6fe failed rc=$OTA_BACK_RC, see $OTA_BACK_LOG -- bench left on 5ec7f0e"
	exit 1
fi
echo "bench back on d97d6fe"

echo "--- kiosk.conf against known-good ---"
CONF=$("$KSSH" "$T" 'cat /data/config/kiosk.conf')
echo "kiosk.conf: $CONF"
if [ "$CONF" != "$KNOWN_GOOD" ]; then
	echo "ABORT: kiosk.conf does not match known-good ('$KNOWN_GOOD')"
	exit 1
fi
echo "KIOSK_CONF_MATCHES_KNOWN_GOOD"

echo "--- e. S4: cards-gated smoothness x3 + soak ---"
one_smoothness() {
	local n=$1
	local out="$OUTDIR/s4-smoothness-run$n.txt"
	for attempt in 1 2; do
		echo "=== S4 smoothness run $n attempt $attempt: polling cards-live ==="
		flock "$LOCK" "$D/poll-cards-live.sh" "$T"
		echo "=== S4 smoothness run $n attempt $attempt starting $(date -u +%FT%TZ) ==="
		[ "$attempt" = 2 ] && rm -f "$out"
		flock "$LOCK" "$D/run-s4-smoothness.sh" "$T" "S4-d97d6fe" "$out"
		rc=$?
		echo "=== S4 smoothness run $n attempt $attempt exit=$rc done $(date -u +%FT%TZ) ==="
		if [ "$rc" != 4 ]; then
			return $rc
		fi
		echo "run $n attempt $attempt VOID (cards not live throughout) -- $([ "$attempt" = 1 ] && echo "retrying once" || echo "giving up, reporting VOID")"
	done
	return 4
}

for n in 1 2 3; do
	one_smoothness "$n"
	echo "S4 smoothness run $n final rc=$?"
done

echo "=== S4 soak: polling cards-live ==="
flock "$LOCK" "$D/poll-cards-live.sh" "$T"
echo "=== S4 soak starting $(date -u +%FT%TZ) ==="
flock "$LOCK" "$D/run-s4-soak.sh" "$T" "S4-d97d6fe" "$OUTDIR/s4-soak.txt"
echo "=== S4 soak exit=$? done $(date -u +%FT%TZ) ==="

echo ORCHESTRATE_LIVE_PROOF_DONE
