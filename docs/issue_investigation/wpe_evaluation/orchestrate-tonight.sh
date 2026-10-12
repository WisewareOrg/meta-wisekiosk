#!/bin/bash
# orchestrate-tonight.sh -- URGENT re-sequence: park hours end soon, so smoothness runs first,
# gated on l>=MIN_LIVE (3 tonight -- one card already closed all evening) instead of the usual
# l=4, back to back. Then the soak (no VOID on live-card count, just records it), then the V1b
# re-enable render-check series (needs no live cards). NO OTA at all tonight -- V3/2.44 is
# dropped; the fixed 2.54 image's own V4/V4b (10/10 rc 0) already serves as the pass case, and
# 2.44's offline-validated stored data serves as the other side. Bench stays on d97d6fe
# throughout. Self .done in an EXIT trap. Output under /home/tjwise/185-evidence/, never /tmp.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-tonight.log.done"' EXIT
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
RENDER_CHECK=/home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check.sh
D=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation
OUTDIR=/home/tjwise/185-evidence/s4
EVIDENCE=/home/tjwise/185-evidence/render-check-validation
KNOWN_GOOD="KIOSK_INSPECTOR=0"
MIN_LIVE=3
mkdir -p "$OUTDIR" "$EVIDENCE"

echo "--- kiosk.conf against known-good before anything ---"
CONF=$("$KSSH" "$T" 'cat /data/config/kiosk.conf')
echo "kiosk.conf: $CONF"
if [ "$CONF" != "$KNOWN_GOOD" ]; then
	echo "ABORT: kiosk.conf does not match known-good ('$KNOWN_GOOD')"
	exit 1
fi
echo "KIOSK_CONF_MATCHES_KNOWN_GOOD"

echo "--- smoothness x3, back to back, gated on l>=$MIN_LIVE ---"
for n in 1 2 3; do
	out="$OUTDIR/s4-smoothness-run$n.txt"
	rm -f "$out"
	echo "=== smoothness run $n: polling l>=$MIN_LIVE ==="
	flock "$LOCK" "$D/poll-cards-live.sh" "$T" "$MIN_LIVE"
	echo "=== smoothness run $n starting $(date -u +%FT%TZ) ==="
	flock "$LOCK" "$D/run-s4-smoothness.sh" "$T" "S4-d97d6fe" "$out" "$MIN_LIVE"
	rc=$?
	cp_lines=$(grep 'CP|' "$out" 2>/dev/null)
	lmin=$(printf '%s\n' "$cp_lines" | grep -oE '\|l=[0-9]+' | grep -oE '[0-9]+' | sort -n | head -1)
	echo "=== smoothness run $n exit=$rc min_l_seen=${lmin:-none} done $(date -u +%FT%TZ) ==="
done

echo "--- soak: polling l>=$MIN_LIVE, then the 1h run (records live fraction, never VOIDs on it) ---"
flock "$LOCK" "$D/poll-cards-live.sh" "$T" "$MIN_LIVE"
echo "=== soak starting $(date -u +%FT%TZ) ==="
flock "$LOCK" "$D/run-s4-soak.sh" "$T" "S4-d97d6fe" "$OUTDIR/s4-soak.txt"
echo "=== soak exit=$? done $(date -u +%FT%TZ) ==="

echo "--- V1b re-run: KIOSK_COG_FEATURES=UseDamagingInformationForCompositing (needs no live cards) ---"
V1B_BACKUP="$EVIDENCE/kiosk.conf.v1b-tonight-orig"
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
	echo "V1b-tonight cog argv=[$argv]"
	out="$EVIDENCE/V1b-tonight.log"
	rm -f "$out"
	for i in 1 2 3 4 5; do
		echo "=== V1b-tonight run $i/5 $(date -u +%FT%TZ) ===" >> "$out"
		"$RENDER_CHECK" "$T" >> "$out" 2>&1
		rc=$?
		echo "V1b-tonight run $i rc=$rc" >> "$out"
	done
	echo "-- V1b-tonight rc tally: $(grep -o 'rc=[0-9]*' "$out" | sort | uniq -c | tr '\n' ' ')"
	echo "-- V1b-tonight stale tiles lines: $(grep 'stale tiles=' "$out" | tr '\n' ' ')"
) 9>"$LOCK" 2>&1 | tee -a "$LOGDIR/render-check-tally.log"

echo "--- final kiosk.conf check ---"
echo "kiosk.conf: $("$KSSH" "$T" 'cat /data/config/kiosk.conf')"
echo "bench stayed on: $("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')"

echo ORCHESTRATE_TONIGHT_DONE
