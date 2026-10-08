#!/bin/bash
# orchestrate-d97d6fe-v4.sh -- waits for the build and for the V1-V3 render-check validation to
# exit, then OTA d97d6fe (the fixed 2.54 default) under the lock, confirms cog's own argv
# carries the feature flag (also checked inside ota-verify-d97d6fe.sh), then V4: 5 render-check
# runs, expected all rc 0. Then V1' (relaunched: V1/V2 were lost to a run_series bug, V1' is
# their replacement on the fixed image): KIOSK_COG_FEATURES=UseDamagingInformationForCompositing
# re-enables the fault on top of d97d6fe's default minus (kiosk-launch appends after a comma, so
# the final feature state is the override, last-one-wins); cog's argv is logged, 5 render-check
# runs (expect rc 3, STALE), plus one independent 15-frame v3-style burst + tile-grid analysis
# (expect nonzero disagreement) proving the override really re-enabled the fault, not just that
# render-check says so. kiosk.conf backed up/restored/cmp-verified. Self .done in an EXIT trap.
# The S4 benchmark set (smoothness/soak) is a separate orchestrator, chained on this one's pid.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-d97d6fe-v4.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
EVIDENCE=/home/tjwise/185-evidence/render-check-validation
T=${BENCH:?ssh target, e.g. root@<bench>}
RENDER_CHECK=/home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check.sh
BUILD_LOG="$LOGDIR/build-d97d6fe.log"
RENDER_CHECK_PID=1878365
mkdir -p "$EVIDENCE"

echo "--- waiting for build-d97d6fe.log.done ---"
until [ -f "$BUILD_LOG.done" ]; do sleep 10; done
if ! grep -q "BUILD_EXIT=0" "$BUILD_LOG"; then
	echo "ABORT: build did not succeed, see $BUILD_LOG"
	exit 1
fi
echo "build OK"

echo "--- waiting for orchestrate-render-check (pid $RENDER_CHECK_PID) to exit ---"
while kill -0 "$RENDER_CHECK_PID" 2>/dev/null; do sleep 10; done
echo "render-check V1-V3 chain exited"

# compensate-v3.sh must run (and release the lock) before this OTA starts, or its "bench is on
# 5ec7f0e" check will see d97d6fe instead and correctly refuse to compensate -- ordering, not a
# race the lock alone would resolve, since compensate-v3 does no OTA of its own to hold the lock.
COMPENSATE_V3_PID=1894520
echo "--- waiting for compensate-v3 (pid $COMPENSATE_V3_PID) to exit ---"
while kill -0 "$COMPENSATE_V3_PID" 2>/dev/null; do sleep 10; done
echo "compensate-v3 exited"

echo "--- OTA + verify d97d6fe (under lock) ---"
OTA_LOG="$LOGDIR/ota-verify-d97d6fe.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-d97d6fe.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: ota-verify failed rc=$OTA_RC, see $OTA_LOG"
	exit 1
fi
echo "ota-verify OK, cog argv carries the feature flag"

echo "--- V4: 5 render-check runs on d97d6fe (under lock) ---"
(
	flock 9
	out="$EVIDENCE/V4-d97d6fe-fixed.log"
	rm -f "$out"
	for i in 1 2 3 4 5; do
		echo "=== V4 run $i/5 $(date -u +%FT%TZ) ===" >> "$out"
		"$RENDER_CHECK" "$T" >> "$out" 2>&1
		rc=$?
		echo "V4 run $i rc=$rc" >> "$out"
	done
	echo "-- V4 rc tally: $(grep -o 'rc=[0-9]*' "$out" | sort | uniq -c | tr '\n' ' ')"
	echo "-- V4 stale tiles lines: $(grep 'stale tiles=' "$out" | tr '\n' ' ')"
) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo "--- V1': KIOSK_COG_FEATURES=UseDamagingInformationForCompositing (re-enable, under lock) ---"
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
V1P_BACKUP="$EVIDENCE/kiosk.conf.v1p-orig"
(
	flock 9
	# Trap installed BEFORE the edit, in THIS subshell: a bare "edit, then restore at the
	# bottom" skips the restore if anything in between dies, including a set -u abort on an
	# unbound variable, which is fatal and does not fall through to a later command.
	restore_v1p() {
		"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$V1P_BACKUP"
		"$KSSH" "$T" 'systemctl restart kiosk'
		"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "${V1P_BACKUP}.after"
		cmp "$V1P_BACKUP" "${V1P_BACKUP}.after" && echo "V1P_RESTORE_IDENTICAL" || echo "V1P_RESTORE_MISMATCH"
	}
	"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$V1P_BACKUP"
	trap restore_v1p EXIT
	"$KSSH" "$T" "sh -s" <<'REMOTE'
C=/data/config/kiosk.conf
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_COG_FEATURES=UseDamagingInformationForCompositing' >> $C
systemctl restart kiosk
REMOTE
	sleep 15
	argv=$("$KSSH" "$T" 'pid=$(pidof cog | cut -d" " -f1); [ -n "$pid" ] && tr "\0" " " < /proc/$pid/cmdline')
	echo "V1' cog argv=[$argv]"

	out="$EVIDENCE/V1p-d97d6fe-reenabled.log"
	rm -f "$out"
	for i in 1 2 3 4 5; do
		echo "=== V1p run $i/5 $(date -u +%FT%TZ) ===" >> "$out"
		"$RENDER_CHECK" "$T" >> "$out" 2>&1
		rc=$?
		echo "V1p run $i rc=$rc" >> "$out"
	done
	echo "-- V1p rc tally: $(grep -o 'rc=[0-9]*' "$out" | sort | uniq -c | tr '\n' ' ')"
	echo "-- V1p stale tiles lines: $(grep 'stale tiles=' "$out" | tr '\n' ' ')"

	echo "-- V1p independent check: 1 v3-style burst + analysis --"
	"$BURST/run-v3-short.sh" "$T" "$EVIDENCE/V1p-v3burst" 1
	dirs=$(ls -d "$EVIDENCE/V1p-v3burst"/control-*/ 2>/dev/null | sort -V)
	python3 "$BURST/analyze_burst_v3.py" V1p $dirs
) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo ORCHESTRATE_D97D6FE_V4_DONE
