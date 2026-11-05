#!/usr/bin/env bash
# Runs `just bootprofile` three times under one hold of the pipeline lock,
# with ~/WiseBenchManager/.venv/bin fixed onto PATH first (bench.env's own
# PATH does not include it -- see the batch-8 baseline incident). No `bench
# test` here: the baseline image is already on bench from the earlier run.
#   bootprofile-3x.sh <outdir>
set -euo pipefail
trap 'echo "bootprofile-3x: failed at line $LINENO (exit $?)" >&2' ERR
outdir=$1
mkdir -p "$outdir"

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

set -a
# shellcheck disable=SC1091
source "$HOME/.config/wisebench/bench.env"
set +a
export PATH="$HOME/WiseBenchManager/.venv/bin:$PATH"
cd "$HOME/meta-wisekiosk"
branch=$(git branch --show-current)

for i in 1 2 3; do
    echo "=== bootprofile run $i ==="
    rc=0
    before_dirs=$(ls -1 records/ 2>/dev/null || true)
    just bootprofile > "$outdir/bootprofile-$i.log" 2>&1 || rc=$?
    git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
    after_dirs=$(ls -1 records/ 2>/dev/null || true)
    record=$(comm -13 <(printf '%s\n' "$before_dirs" | sort) <(printf '%s\n' "$after_dirs" | sort) | while read -r d; do
        [ -f "records/$d/report.jsonl" ] && printf '%s\n' "records/$d"
    done | tail -1)
    echo "bootprofile run $i exit=$rc record=${record:-none}" | tee -a "$outdir/bootprofile-$i.log"
done

touch "$outdir/DONE"
echo "bootprofile 3x complete"
