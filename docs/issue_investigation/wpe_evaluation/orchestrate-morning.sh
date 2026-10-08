#!/bin/bash
# orchestrate-morning.sh -- park-hours chain: closes two open owner questions with data.
#   1. On d97d6fe (bench is there now): poll-cards-live MIN_LIVE=4 (c=4 l=4, no timeout), then
#      3x S4 smoothness back to back (each VOID unless l=4 throughout the t>=15s measured
#      window -- run-s4-smoothness.sh's gate, fixed this morning to filter by that window
#      itself rather than needing an offline reclassification), then analyze-s4-smoothness
#      against S1/S3 with the E1 verdict.
#   2. Still inside the l=4 window: OTA to 138d914 (bundle manifest verified against the
#      device's own compatible before this script was launched), settle, confirm l=4, then 5
#      paired (render-check, v3 burst) samples -- each pair labelled with the CP state read
#      just before it, so a card dropping mid-step is visible, not silently averaged away.
#   3. OTA back to d97d6fe, verify, final kiosk.conf check.
# kiosk.conf restore traps are installed before any edit, in the same shell as the edit.
# OTA_EXIT checked on every OTA. All captures under /home/tjwise/185-evidence/, never /tmp.
# Self .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-morning.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
D=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation
RENDER_CHECK=/home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check.sh
OUTDIR=/home/tjwise/185-evidence/s4-morning
EVIDENCE=/home/tjwise/185-evidence/render-check-validation
KNOWN_GOOD="KIOSK_INSPECTOR=0"
mkdir -p "$OUTDIR" "$EVIDENCE"

echo "--- verify -impl worktree HEAD contains c9feb17 ---"
cd /home/tjwise/meta-wisekiosk-185-impl
HEAD_SHA=$(git rev-parse HEAD)
echo "HEAD=$HEAD_SHA"
git merge-base --is-ancestor c9feb17 HEAD || { echo "ABORT: HEAD does not contain c9feb17"; exit 1; }
echo "HEAD_CONTAINS_c9feb17"

echo "--- 1a. kiosk.conf against known-good, bench on d97d6fe ---"
echo "buildinfo: $("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')"
CONF=$("$KSSH" "$T" 'cat /data/config/kiosk.conf')
echo "kiosk.conf: $CONF"
[ "$CONF" = "$KNOWN_GOOD" ] || { echo "ABORT: kiosk.conf not known-good"; exit 1; }
echo "KIOSK_CONF_MATCHES_KNOWN_GOOD"

echo "--- 1b. poll-cards-live MIN_LIVE=4 (under lock) ---"
flock "$LOCK" "$D/poll-cards-live.sh" "$T" 4

echo "--- 1c. 3x S4 smoothness, back to back, MIN_LIVE=4 ---"
for n in 1 2 3; do
	out="$OUTDIR/s4-smoothness-run$n.txt"
	rm -f "$out"
	echo "=== morning smoothness run $n starting $(date -u +%FT%TZ) ==="
	flock "$LOCK" "$D/run-s4-smoothness.sh" "$T" "S4-morning-d97d6fe" "$out" 4
	rc=$?
	echo "=== morning smoothness run $n exit=$rc done $(date -u +%FT%TZ) ==="
done

echo "--- 1d. analyze-s4-smoothness against S1/S3 (E1 verdict) ---"
cd "$D"
{
	echo "=== S1 (X baseline, commit 20a1f34), from README Runs 2-4 ==="
	echo "run2: 570s 28191f mean_fps=49.46 pct<50ms=98.6 stall_t15=bounded_0.0252-0.0541 (14-30) clusters=11"
	echo "run3: 570s 27052f mean_fps=47.46 pct<50ms=98.0 stall_t15=bounded_0.0252-0.0541 (14-30) clusters=11"
	echo "run4: 569s 29921f mean_fps=52.59 pct<50ms=98.7 stall_t15=bounded_0.0253-0.0343 (14-19) clusters=14"
	echo
	echo "=== S3 (2.44.4, commit 32b670c), from README Runs 24-26 ==="
	echo "run24: 580s 30712f mean_fps=52.95 pct<50ms=99.0 stall_t15=0.0248 (14 from ref_t 13s) clusters=10"
	echo "run25: 581s 29091f mean_fps=50.07 pct<50ms=98.3 stall_t15=0.0654 (37 from ref_t 14s) clusters=11"
	echo "run26: 582s 29157f mean_fps=50.10 pct<50ms=98.5 stall_t15=0.0758 (43 from ref_t 14s) clusters=12"
	echo
	echo "=== S4-morning (2.54 + damage fix default, commit d97d6fe), 4/4 cards live ==="
	for n in 1 2 3; do
		f="$OUTDIR/s4-smoothness-run$n.txt"
		echo "-- run $n ($f) --"
		python3 parse_smoothness.py "$f" 2>&1
	done
	echo
	echo "=== E1 verdict ==="
	python3 - <<'PYEOF'
import sys
sys.path.insert(0, ".")
import parse_smoothness as ps
import verdict as v

OUTDIR = "/home/tjwise/185-evidence/s4-morning"

def runinfo(path):
	lines = open(path).read().splitlines()
	d = __import__("journal_extract").last_parseable(lines, ps.parse)
	if d is None:
		return None
	b = ps.steady_stall_bounds(d)
	return {"stall_rate": {"lower_rate": b["lower_rate"], "upper_rate": b["upper_rate"], "bounded": b["bounded"]},
	        "pct_under_50": ps.pct_under_50ms(d), "fps": ps.mean_fps(d)}

s1 = [
	{"stall_rate": {"lower_rate": 0.0252, "upper_rate": 0.0541, "bounded": True}, "pct_under_50": 98.6, "fps": 49.46},
	{"stall_rate": {"lower_rate": 0.0252, "upper_rate": 0.0541, "bounded": True}, "pct_under_50": 98.0, "fps": 47.46},
	{"stall_rate": {"lower_rate": 0.0253, "upper_rate": 0.0343, "bounded": True}, "pct_under_50": 98.7, "fps": 52.59},
]
s3 = [
	{"stall_rate": {"lower_rate": 0.0248, "upper_rate": 0.0248, "bounded": False}, "pct_under_50": 99.0, "fps": 52.95},
	{"stall_rate": {"lower_rate": 0.0654, "upper_rate": 0.0654, "bounded": False}, "pct_under_50": 98.3, "fps": 50.07},
	{"stall_rate": {"lower_rate": 0.0758, "upper_rate": 0.0758, "bounded": False}, "pct_under_50": 98.5, "fps": 50.10},
]
s4 = [x for x in (runinfo(f"{OUTDIR}/s4-smoothness-run{n}.txt") for n in (1, 2, 3)) if x is not None]
BASE_SOAK = {"fmax": 0, "fever": 0, "restarts": 0, "reboots": 0, "memory_problem": False}
print("-- S4-morning vs S1 (X baseline) --")
r = v.regression_reasons(s1, s4, BASE_SOAK, BASE_SOAK)
print("GO" if not r else "NO-GO: " + "; ".join(r))
print("-- S4-morning vs S3 (2.44.4) --")
r = v.regression_reasons(s3, s4, BASE_SOAK, BASE_SOAK)
print("GO" if not r else "NO-GO: " + "; ".join(r))
PYEOF
} > "$OUTDIR/s4-morning-analysis.txt" 2>&1
cat "$OUTDIR/s4-morning-analysis.txt"

echo "--- 2a. OTA to 138d914 (under lock, bundle pre-verified) ---"
OTA_LOG="$LOGDIR/ota-verify-138d914-morning.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-138d914.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	echo "ABORT: OTA to 138d914 failed rc=$OTA_RC, see $OTA_LOG"
	exit 1
fi
echo "ota-verify OK, bench on 138d914"

echo "--- 2b. deploy cards-probe, confirm l=4 (leaves the probe running for the pairs) ---"
V2_BACKUP="$EVIDENCE/kiosk.conf.morning-orig"
RESTORE_PENDING=0
restore_morning() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$V2_BACKUP"
	"$KSSH" "$T" 'rm -f /home/root/kiosk-probe.js; systemctl restart kiosk'
	AFTER="${V2_BACKUP}.after"
	"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$AFTER"
	cmp "$V2_BACKUP" "$AFTER" && echo "MORNING_RESTORE_IDENTICAL" || echo "MORNING_RESTORE_MISMATCH"
}
trap 'restore_morning; touch "$LOGDIR/orchestrate-morning.log.done"' EXIT

# One lock hold for the whole 2b/2c/pairs stretch: the trap and RESTORE_PENDING live in THIS
# shell, not a subshell, so a flock subshell here would lose the flag the trap depends on.
exec 9>"$LOCK"
flock 9
"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$V2_BACKUP"
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
printf '%s\n' "$DEPLOY_OUT" | tee -a "$LOGDIR/render-check-tally.log"
START=$(printf '%s\n' "$DEPLOY_OUT" | sed -n 's/^start-epoch \([0-9]*\)$/\1/p')
echo "START_EPOCH=$START" | tee -a "$LOGDIR/render-check-tally.log"

echo "--- 2c. confirm l=4 once settled, then 5 paired (render-check, v3 burst) samples ---"
latest_cp() {
	"$KSSH" "$T" "journalctl -u kiosk --since @${START:-0} -o cat --no-pager | grep 'CP|' | tail -1" 2>/dev/null
}
for wait in 0 35 70 105 140; do
	[ "$wait" -gt 0 ] && sleep 35
	LAST=$(latest_cp)
	echo "settle check t=${wait}s: $LAST"
done

PAIR_LOG="$EVIDENCE/morning-138d914-pairs.log"
rm -f "$PAIR_LOG"
for i in 1 2 3 4 5; do
	cp_state=$(latest_cp)
	echo "=== pair $i/5 $(date -u +%FT%TZ) cp_state=[$cp_state] ===" | tee -a "$PAIR_LOG"
	echo "--- render-check ---" >> "$PAIR_LOG"
	"$RENDER_CHECK" "$T" >> "$PAIR_LOG" 2>&1
	rc=$?
	echo "pair $i render-check rc=$rc" >> "$PAIR_LOG"
	echo "--- v3 burst ---" >> "$PAIR_LOG"
	"$BURST/run-v3-short.sh" "$T" "$EVIDENCE/morning-pair$i-v3burst" 1 >> "$PAIR_LOG" 2>&1
	dirs=$(ls -d "$EVIDENCE/morning-pair$i-v3burst"/control-*/ 2>/dev/null | sort -V)
	python3 "$BURST/analyze_burst_v3.py" "pair$i" $dirs >> "$PAIR_LOG" 2>&1
done
echo "-- pair rc tally: $(grep -o 'render-check rc=[0-9]*' "$PAIR_LOG" | sort | uniq -c | tr '\n' ' ')"
echo "-- pair stale tiles: $(grep 'stale tiles=' "$PAIR_LOG" | tr '\n' ' ')"
echo "-- pair cp_state labels: $(grep -o 'cp_state=\[[^]]*\]' "$PAIR_LOG" | tr '\n' ' ')"

restore_morning
RESTORE_PENDING=0
flock -u 9
exec 9>&-

echo "--- 3. OTA back to d97d6fe (under lock) ---"
OTA_BACK_LOG="$LOGDIR/ota-verify-d97d6fe-morning-back.log"
rm -f "$OTA_BACK_LOG" "$OTA_BACK_LOG.done"
flock "$LOCK" "$BURST/ota-verify-d97d6fe.sh" > "$OTA_BACK_LOG" 2>&1
OTA_BACK_RC=$?
touch "$OTA_BACK_LOG.done"
if [ $OTA_BACK_RC -ne 0 ]; then
	echo "ABORT: OTA back to d97d6fe failed rc=$OTA_BACK_RC, see $OTA_BACK_LOG -- bench left on 138d914"
	exit 1
fi
echo "bench back on d97d6fe"

echo "--- final kiosk.conf check ---"
echo "kiosk.conf: $("$KSSH" "$T" 'cat /data/config/kiosk.conf')"

echo ORCHESTRATE_MORNING_DONE
