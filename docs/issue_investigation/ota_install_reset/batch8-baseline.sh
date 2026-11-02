#!/usr/bin/env bash
# Batch-8 perf baseline, attempt 1: puts <sha> on bench, then profiles 3
# boots. Holds the pipeline lock for the whole run (not per step). Its
# bootprofile step has a known bug (bare `just bootprofile`, no
# ~/WiseBenchManager/.venv/bin on PATH -- see the README's Batch 8 section),
# which is why it never ran past the `bench test` step here: that step
# caught reset 6. Kept as the exact script that caught it, not corrected;
# batch8-bootprofile-3x.sh is the fixed successor that produced the counted
# baseline.
#   batch8-baseline.sh <sha> <outdir>
set -euo pipefail
trap 'echo "baseline: failed at line $LINENO (exit $?)" >&2' ERR
sha=$1
outdir=$2
mkdir -p "$outdir"

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

set -a
# shellcheck disable=SC1091
source "$HOME/.config/wisebench/bench.env"
set +a
cd "$HOME/meta-wisekiosk"
bench="$HOME/WiseBenchManager/.venv/bin/bench"
branch=$(git branch --show-current)

echo "=== bench test $sha (puts the baseline image on bench) ==="
status=0
"$bench" test "$sha" > "$outdir/bench-test.log" 2>&1 || status=$?
git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
echo "bench test exit=$status" | tee -a "$outdir/bench-test.log"
if [ "$status" -ne 0 ]; then
    echo "baseline: bench test failed (exit $status), not proceeding to bootprofile" >&2
    exit 1
fi

for i in 1 2 3; do
    echo "=== bootprofile run $i ==="
    rc=0
    just bootprofile > "$outdir/bootprofile-$i.log" 2>&1 || rc=$?
    git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
    echo "bootprofile run $i exit=$rc" | tee -a "$outdir/bootprofile-$i.log"
done

touch "$outdir/DONE"
echo "baseline run complete"
