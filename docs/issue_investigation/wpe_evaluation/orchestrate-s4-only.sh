#!/bin/bash
# orchestrate-s4-only.sh -- S4 benchmark set (cards-gated smoothness x3 + soak) on d97d6fe,
# standalone for an unattended overnight run: bench is already on d97d6fe with kiosk.conf
# known-good (confirmed immediately before launch), so no OTA or pid-chaining needed. Self
# .done in an EXIT trap. Output under /home/tjwise/185-evidence/s4/, never /tmp.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-s4-only.log.done"' EXIT
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
D=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation
OUTDIR=/home/tjwise/185-evidence/s4
KNOWN_GOOD="KIOSK_INSPECTOR=0"
mkdir -p "$OUTDIR"

echo "--- buildinfo + kiosk.conf against known-good ---"
echo "buildinfo: $("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')"
CONF=$("$KSSH" "$T" 'cat /data/config/kiosk.conf')
echo "kiosk.conf: $CONF"
if [ "$CONF" != "$KNOWN_GOOD" ]; then
	echo "ABORT: kiosk.conf does not match known-good ('$KNOWN_GOOD')"
	exit 1
fi
echo "KIOSK_CONF_MATCHES_KNOWN_GOOD"

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

echo ALL_S4_SMOOTHNESS_SOAK_DONE
