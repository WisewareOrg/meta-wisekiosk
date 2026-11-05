#!/usr/bin/env bash
# One `bench test` run against a pushed sha, under the pipeline lock the
# ~/wisekiosk-bench checkout's bench-run.timer also takes, so the timer backs
# off rather than interleaving with this checkout.
#
#   run-bench-test.sh <sha>
set -euo pipefail
[ -n "${1:-}" ] || { echo "usage: run-bench-test.sh <sha>" >&2; exit 2; }
sha=$1

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

set -a
# shellcheck disable=SC1091
source "$HOME/.config/wisebench/bench.env"
set +a
cd "$HOME/meta-wisekiosk"
"$HOME/WiseBenchManager/.venv/bin/bench" test "$sha"
