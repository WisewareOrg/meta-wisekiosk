#!/bin/bash
# orchestrate-s4-smoothness-soak.sh -- the S4 benchmark set on d97d6fe (2.54 with the damage
# fix default): 3 smoothness runs then a 1h soak, each gated on the cards-live probe
# (poll-cards-live.sh, cards-probe.js: c=4 l=4). Waits for orchestrate-d97d6fe-v4 to exit. A
# smoothness run whose capture isn't c=4 l=4 throughout is VOID and rerun once (after re-polling
# live); a second VOID is reported, not retried again. The soak records the cards-live fraction
# but never VOIDs on it. Self .done in an EXIT trap. Output under /home/tjwise/185-evidence/s4/,
# never /tmp.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-s4-smoothness-soak.log.done"' EXIT
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
D=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation
OUTDIR=/home/tjwise/185-evidence/s4
V4_PID=1894760
mkdir -p "$OUTDIR"

echo "--- waiting for orchestrate-d97d6fe-v4 (pid $V4_PID) to exit ---"
while kill -0 "$V4_PID" 2>/dev/null; do sleep 10; done
if ! grep -q "ORCHESTRATE_D97D6FE_V4_DONE" "$LOGDIR/orchestrate-d97d6fe-v4.log"; then
	echo "ABORT: the d97d6fe/V4 chain did not complete cleanly, see $LOGDIR/orchestrate-d97d6fe-v4.log"
	exit 1
fi
echo "d97d6fe/V4 chain OK, bench is on d97d6fe"

# compensate-v1p.sh must run (and fix kiosk.conf if V1' left it dirty) before smoothness/soak
# touches the device -- same ordering reason as compensate-v3 vs the d97d6fe OTA.
COMPENSATE_V1P_PID=1897699
echo "--- waiting for compensate-v1p (pid $COMPENSATE_V1P_PID) to exit ---"
while kill -0 "$COMPENSATE_V1P_PID" 2>/dev/null; do sleep 10; done
echo "compensate-v1p exited"

KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
KNOWN_GOOD="KIOSK_INSPECTOR=0"
echo "--- kiosk.conf against known-good before touching the device ---"
CONF=$("$KSSH" "$T" 'cat /data/config/kiosk.conf')
echo "kiosk.conf: $CONF"
if [ "$CONF" != "$KNOWN_GOOD" ]; then
	echo "ABORT: kiosk.conf does not match known-good ('$KNOWN_GOOD'); refusing to benchmark against a contaminated config"
	exit 1
fi
echo "KIOSK_CONF_MATCHES_KNOWN_GOOD"

# one_smoothness <n> -- run $n (1..3), with one automatic rerun on a cards-live VOID.
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
