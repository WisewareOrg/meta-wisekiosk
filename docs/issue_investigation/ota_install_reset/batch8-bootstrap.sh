#!/usr/bin/env bash
# Batch-8 bootstrap: one `bench test <sha>` to get the soft-lockup-detector
# kernel onto bench, outside loop8.sh and not counted as one of its runs --
# loop8.sh enforces its watchdog_thresh step uniformly from run 1, which
# needs the new kernel already there. Holds the pipeline lock for the run.
#   batch8-bootstrap.sh <sha> <outdir>
set -euo pipefail
trap 'echo "bootstrap: failed at line $LINENO (exit $?)" >&2' ERR
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

before_dirs=$(ls -1 records/ 2>/dev/null || true)
status=0
"$bench" test "$sha" > "$outdir/bench-test.log" 2>&1 || status=$?
git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
after_dirs=$(ls -1 records/ 2>/dev/null || true)
record=$(comm -13 <(printf '%s\n' "$before_dirs" | sort) <(printf '%s\n' "$after_dirs" | sort) | while read -r d; do
    [ -f "records/$d/run.json" ] && printf '%s\n' "records/$d"
done | tail -1)
echo "bootstrap bench test exit=$status record=${record:-none}" | tee -a "$outdir/bench-test.log"

touch "$outdir/DONE"
echo "bootstrap complete"
