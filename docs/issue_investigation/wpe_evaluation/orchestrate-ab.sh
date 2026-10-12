#!/bin/bash
# orchestrate-ab.sh -- same-day, same-page A/B/C smoothness comparison, queued behind
# orchestrate-cog-core (waits for its pid, never edits it).
#   A. 138d914 (pre-fix 2.54): OTA explicitly, no-timeout cards gate (c=4 l=4,
#      poll-cards-live.sh, which aborts on a kiosk restart or a FROZEN board rather than
#      waiting forever on a genuinely bad one) before each of 3 smoothness runs.
#   B. X baseline, built from origin/main (SHA recorded) in a fresh worktree/build dir, shared
#      DL_DIR/SSTATE/hashserv, no lock while building (host only). OTA once built, the same
#      no-timeout cards gate (X variant: poll-cards-live-x.sh, title-based since X has no
#      console-to-journal channel) before each of 3 runs. Smoothness via the committed S1
#      driver, run-appliance.sh, unchanged, prefix MP sleep 585 len 20000 -- the exact
#      parameters the README's S1 Runs 2-4 used -- with an inlined pre-run settle check
#      standing in for the historic run-smoothness.sh@ea79e18 wrapper (not checked out in any
#      live worktree).
#   C. Back to d97d6fe: OTA, the same cards gate before each of 3 runs, run-s4-smoothness.sh.
# An OTA script's OWN internal settle check (its 20-min bound) is advisory here, not fatal: the
# cards gate is the real readiness signal per the owner's ruling that the slow fill is the
# app's own too-short timeout, unrelated to browser performance -- this investigation does not
# measure or label page-fill time, it only waits for like-for-like page state before capturing.
# Then the E1 verdicts for C vs B (fixed vs X, same day) and C vs A (fix cost). Evidence under
# /home/tjwise/185-evidence/s4-ab/, never /tmp. kiosk.conf/script.js restore traps installed
# before every edit. OTA_EXIT checked on every OTA. Self .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/orchestrate-ab.log.done"' EXIT
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
LOCK=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/bench.lock
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
D=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation
GPU=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/gpu_compositing
OUTDIR=/home/tjwise/185-evidence/s4-ab
COG_CORE_PID=2904437
BUILD_LOG="$LOGDIR/build-main-ab.log"
mkdir -p "$OUTDIR"

echo "--- waiting for orchestrate-cog-core (pid $COG_CORE_PID) to exit ---"
while kill -0 "$COG_CORE_PID" 2>/dev/null; do sleep 15; done
echo "orchestrate-cog-core exited"

# settle_screenshot -- the same mean>=10 pre-run check every other driver in this investigation
# uses, for drivers (run-appliance.sh) that don't have it built in.
settle_screenshot() {
	local shot="$OUTDIR/.settle-$$.png"
	rm -f "$shot"
	local settle_start
	settle_start=$(date +%s)
	local i elapsed
	for i in $(seq 1 120); do
		if [ "$i" -gt 1 ]; then rm -f "$shot"; sleep 10; fi
		local out
		out=$(/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-screenshot.sh "$T" "$shot")
		local rc=$?
		printf '%s\n' "$out"
		local mean
		mean=$(printf '%s\n' "$out" | sed -n 's/^min=.* mean=\([0-9.]*\)$/\1/p')
		elapsed=$(( $(date +%s) - settle_start ))
		if [ $rc -eq 0 ] && awk -v m="${mean:-0}" 'BEGIN { exit !(m >= 10) }'; then
			echo "settled at t=${elapsed}s, mean=$mean"
			rm -f "$shot"
			return 0
		fi
	done
	echo "did not settle within ${elapsed}s"
	rm -f "$shot"
	return 1
}

# ota_settle_is_advisory <log> -- true iff the ONLY abort reason in an ota-verify-*.sh log was
# its own internal settle timeout (install, buildinfo and boot-counter all already passed) --
# in which case it is not fatal here, because the cards gate that runs next is the real
# readiness signal and has no timeout of its own.
ota_settle_is_advisory() {
	grep -q "did not settle within" "$1" && grep -q "BUILDINFO_MATCH" "$1"
}

echo "=================== A: 138d914 (pre-fix 2.54) ==================="
OTA_LOG="$LOGDIR/ota-verify-138d914-ab.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-138d914.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	if ota_settle_is_advisory "$OTA_LOG"; then
		echo "A: OTA install/buildinfo/boot-counter OK, only the OTA script's own settle timed out -- not fatal, the cards gate below is the real signal"
	else
		echo "ABORT: OTA to 138d914 failed rc=$OTA_RC, see $OTA_LOG"
		exit 1
	fi
fi
echo "A: ota-verify done, bench on 138d914"

for n in 1 2 3; do
	out="$OUTDIR/A-138d914-run$n.txt"
	rm -f "$out"
	echo "--- A run $n: l=4 gate ---"
	flock "$LOCK" "$D/poll-cards-live.sh" "$T" 4
	echo "=== A run $n starting $(date -u +%FT%TZ) ==="
	flock "$LOCK" "$D/run-s4-smoothness.sh" "$T" "AB-A-138d914" "$out" 4
	rc=$?
	echo "=== A run $n exit=$rc done $(date -u +%FT%TZ) ==="
done

echo "=================== B: X baseline (origin/main) ==================="
echo "--- waiting for the X build ---"
until [ -f "$BUILD_LOG.done" ]; do sleep 15; done
if ! grep -q "BUILD_EXIT=0" "$BUILD_LOG"; then
	echo "ABORT: X build did not succeed, see $BUILD_LOG"
	exit 1
fi
echo "X build OK"

OTA_LOG="$LOGDIR/ota-verify-main-ab.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-main-ab.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	if ota_settle_is_advisory "$OTA_LOG"; then
		echo "B: OTA install/buildinfo/boot-counter OK, only the OTA script's own settle timed out -- not fatal, the cards gate below is the real signal"
	else
		echo "ABORT: OTA to the X image failed rc=$OTA_RC, see $OTA_LOG"
		exit 1
	fi
fi
echo "B: ota-verify done, bench on the X image"

echo "--- B: exercising x-cards-probe.js once on the live X session, logging what it reads ---"
flock "$LOCK" "$D/check-cards-once-x.sh" "$T"

P7_SHA=$(sha256sum < "$GPU/p7_min.js" | cut -d' ' -f1)
echo "p7_min.js sha256 (the only probe B's capture window ever loads): $P7_SHA"

for n in 1 2 3; do
	out="$OUTDIR/B-X-run$n.txt"
	rm -f "$out"
	echo "--- B run $n: l=4 gate (X variant, cards verified at START -- x-cards-probe runs ONLY here, never during the capture) ---"
	flock "$LOCK" "$D/poll-cards-live-x.sh" "$T" 4
	echo "--- B run $n: pre-run settle check ---"
	flock "$LOCK" bash -c "$(declare -f settle_screenshot); settle_screenshot" || {
		echo "ABORT: B run $n pre-run screenshot did not settle"; continue
	}
	echo "=== B run $n starting $(date -u +%FT%TZ) -- script.js is p7_min.js alone for this entire window ==="
	flock "$LOCK" "$GPU/run-appliance.sh" "$T" "AB-B-X" "$GPU/p7_min.js" MP 585 20000 "$out"
	rc=$?
	echo "=== B run $n exit=$rc done $(date -u +%FT%TZ) ==="
	DEPLOYED_SHA=$(grep -oE '^# probe sha256 deployed [0-9a-f]+' "$out" 2>/dev/null | awk '{print $NF}')
	echo "B run $n deployed probe sha256: ${DEPLOYED_SHA:-<not found in $out>} (expect $P7_SHA)"
	echo "--- B run $n: cards check at END (x-cards-probe runs again now that p7_min's window is closed) ---"
	flock "$LOCK" "$D/check-cards-once-x.sh" "$T"
	echo "B run $n label: cards verified at start and end (no in-run samples -- X has no separate channel from p7_min's own title use)"
done

echo "=================== C: back to d97d6fe ==================="
OTA_LOG="$LOGDIR/ota-verify-d97d6fe-ab.log"
rm -f "$OTA_LOG" "$OTA_LOG.done"
flock "$LOCK" "$BURST/ota-verify-d97d6fe.sh" > "$OTA_LOG" 2>&1
OTA_RC=$?
touch "$OTA_LOG.done"
if [ $OTA_RC -ne 0 ]; then
	if ota_settle_is_advisory "$OTA_LOG"; then
		echo "C: OTA install/buildinfo/boot-counter OK, only the OTA script's own settle timed out -- not fatal, the cards gate below is the real signal"
		# The script exits before its own argv check when settle fails -- redo it here so that
		# verification isn't silently skipped on the advisory path.
		ARGV=$("$KSSH" "$T" 'pid=$(pidof cog | cut -d" " -f1); [ -n "$pid" ] && tr "\0" " " < /proc/$pid/cmdline')
		echo "C: cog argv=[$ARGV]"
		case "$ARGV" in
		*"--features=-UseDamagingInformationForCompositing"*) echo "C: ARGV_MATCH" ;;
		*) echo "ABORT: cog argv does not carry the expected --features= flag"; exit 1 ;;
		esac
	else
		echo "ABORT: OTA back to d97d6fe failed rc=$OTA_RC, see $OTA_LOG"
		exit 1
	fi
fi
echo "C: ota-verify done, bench back on d97d6fe"

for n in 1 2 3; do
	out="$OUTDIR/C-d97d6fe-run$n.txt"
	rm -f "$out"
	echo "--- C run $n: l=4 gate ---"
	flock "$LOCK" "$D/poll-cards-live.sh" "$T" 4
	echo "=== C run $n starting $(date -u +%FT%TZ) ==="
	flock "$LOCK" "$D/run-s4-smoothness.sh" "$T" "AB-C-d97d6fe" "$out" 4
	rc=$?
	echo "=== C run $n exit=$rc done $(date -u +%FT%TZ) ==="
done

echo "--- final kiosk.conf check ---"
echo "kiosk.conf: $("$KSSH" "$T" 'cat /data/config/kiosk.conf')"

echo "=================== ANALYSIS: A / B / C, E1 verdicts C-vs-B and C-vs-A ==================="
cd "$D"
{
	for label_dir in "A:A-138d914" "B:B-X" "C:C-d97d6fe"; do
		label=${label_dir%%:*}
		pfx=${label_dir#*:}
		echo "=== $label ($pfx) ==="
		for n in 1 2 3; do
			f="$OUTDIR/$pfx-run$n.txt"
			[ -e "$f" ] || { echo "-- run $n: MISSING ($f) --"; continue; }
			echo "-- run $n ($f) --"
			grep -E '^# started|^# capture start|^# capture end' "$f"
			python3 parse_smoothness.py "$f" 2>&1
		done
		echo
	done
	echo "=== E1 verdicts ==="
	python3 - <<'PYEOF'
import sys
sys.path.insert(0, ".")
import parse_smoothness as ps
import verdict as v

OUTDIR = "/home/tjwise/185-evidence/s4-ab"

def runinfo(path):
	try:
		lines = open(path).read().splitlines()
	except OSError:
		return None
	d = __import__("journal_extract").last_parseable(lines, ps.parse)
	if d is None:
		return None
	b = ps.steady_stall_bounds(d)
	return {"stall_rate": {"lower_rate": b["lower_rate"], "upper_rate": b["upper_rate"], "bounded": b["bounded"]},
	        "pct_under_50": ps.pct_under_50ms(d), "fps": ps.mean_fps(d)}

A = [x for x in (runinfo(f"{OUTDIR}/A-138d914-run{n}.txt") for n in (1, 2, 3)) if x is not None]
B = [x for x in (runinfo(f"{OUTDIR}/B-X-run{n}.txt") for n in (1, 2, 3)) if x is not None]
C = [x for x in (runinfo(f"{OUTDIR}/C-d97d6fe-run{n}.txt") for n in (1, 2, 3)) if x is not None]
BASE_SOAK = {"fmax": 0, "fever": 0, "restarts": 0, "reboots": 0, "memory_problem": False}
print(f"A (138d914) usable runs: {len(A)}; B (X) usable runs: {len(B)}; C (d97d6fe) usable runs: {len(C)}")
print("-- C vs B (fixed 2.54 vs X baseline, same day) --")
if B and C:
	r = v.regression_reasons(B, C, BASE_SOAK, BASE_SOAK)
	print("GO" if not r else "NO-GO: " + "; ".join(r))
else:
	print("CANNOT JUDGE: missing runs")
print("-- C vs A (did the fix cost anything vs pre-fix 2.54, same day) --")
if A and C:
	r = v.regression_reasons(A, C, BASE_SOAK, BASE_SOAK)
	print("GO" if not r else "NO-GO: " + "; ".join(r))
else:
	print("CANNOT JUDGE: missing runs")
PYEOF
} > "$OUTDIR/ab-analysis.txt" 2>&1
cat "$OUTDIR/ab-analysis.txt"

echo ORCHESTRATE_AB_DONE
