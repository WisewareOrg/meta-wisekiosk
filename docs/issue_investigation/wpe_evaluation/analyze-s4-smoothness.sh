#!/bin/bash
# analyze-s4-smoothness.sh -- waits for S4 smoothness run 3 to finish, then runs the committed
# parse_smoothness.py on runs 1-3 and reports mean fps / %<50ms / steady stall rate / cluster
# spacing, beside S1 (X baseline, runs 2-4) and S3 (2.44.4, runs 24-26) from the README, with
# the E1 verdict (verdict.py's regression_reasons) against each. Notes 3-of-4-cards-live. Output
# to a file, not /tmp (under 185-evidence). Self .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/analyze-s4-smoothness.log.done"' EXIT
TONIGHT_LOG="$LOGDIR/orchestrate-tonight.log"
OUTDIR=/home/tjwise/185-evidence/s4
D=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation
OUT=/home/tjwise/185-evidence/s4/s4-smoothness-analysis.txt

echo "--- waiting for smoothness run 3 to finish ---"
until grep -q "smoothness run 3 exit=" "$TONIGHT_LOG" 2>/dev/null; do sleep 10; done
echo "run 3 done, analyzing"

cd "$D"
{
	echo "S4 smoothness analysis (3 of 4 park cards live tonight -- one closed for the night)"
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
	echo "=== 2.54 pre-fix (f4d4bb8), cards judged by eye -- predates the DOM gate, this morning ==="
	PREFIX_DIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/s4
	for n in 1 2 3; do
		f="$PREFIX_DIR/s4-smoothness-run$n.txt"
		actual=$(grep -m1 "buildinfo" "$f" | grep -o 'f4d4bb8[0-9a-f]*')
		echo "-- run $n ($f), buildinfo $actual --"
		if [ -z "$actual" ]; then
			echo "SKIPPED: buildinfo did not match f4d4bb8"
			continue
		fi
		python3 parse_smoothness.py "$f" 2>&1
	done
	echo
	echo "=== S4 (2.54 + damage fix default, commit d97d6fe), tonight, 3/4 cards live ==="
	for n in 1 2 3; do
		f="$OUTDIR/s4-smoothness-run$n.txt"
		echo "-- run $n ($f) --"
		python3 parse_smoothness.py "$f" 2>&1
	done
	echo
	echo "=== E1 verdict (verdict.py's regression_reasons) ==="
	python3 - <<'PYEOF'
import sys, re
sys.path.insert(0, ".")
import parse_smoothness as ps

OUTDIR = "/home/tjwise/185-evidence/s4"

def runinfo(path):
    lines = open(path).read().splitlines()
    d = __import__("journal_extract").last_parseable(lines, ps.parse)
    if d is None:
        return None
    b = ps.steady_stall_bounds(d)
    return {"stall_rate": {"lower_rate": b["lower_rate"], "upper_rate": b["upper_rate"],
                            "bounded": b["bounded"]},
            "pct_under_50": ps.pct_under_50ms(d), "fps": ps.mean_fps(d)}

# S1 baseline, S3 2.44.4 -- hardcoded from the README tables cited above (bounded stall_rate
# pairs taken as-is; exact runs get lower_rate==upper_rate).
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
s4 = [runinfo(f"{OUTDIR}/s4-smoothness-run{n}.txt") for n in (1, 2, 3)]
s4 = [x for x in s4 if x is not None]

PREFIX_DIR = "/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/s4"
s4_prefix = [runinfo(f"{PREFIX_DIR}/s4-smoothness-run{n}.txt") for n in (1, 2, 3)]
s4_prefix = [x for x in s4_prefix if x is not None]

import verdict as v
BASE_SOAK = {"fmax": 0, "fever": 0, "restarts": 0, "reboots": 0, "memory_problem": False}
print("-- S4 fixed vs S1 (X baseline) --")
r = v.regression_reasons(s1, s4, BASE_SOAK, BASE_SOAK)
print("GO" if not r else "NO-GO: " + "; ".join(r))
print("-- S4 fixed vs S3 (2.44.4) --")
r = v.regression_reasons(s3, s4, BASE_SOAK, BASE_SOAK)
print("GO" if not r else "NO-GO: " + "; ".join(r))
print("-- S4 fixed vs 2.54 pre-fix (f4d4bb8) -- did turning the damage feature off cost smoothness? --")
r = v.regression_reasons(s4_prefix, s4, BASE_SOAK, BASE_SOAK)
print("GO (no regression vs pre-fix)" if not r else "NO-GO: " + "; ".join(r))
PYEOF
} > "$OUT" 2>&1

echo "wrote $OUT"
cat "$OUT"
echo ANALYZE_S4_SMOOTHNESS_DONE
