#!/usr/bin/env bash
# Repeat `bench test <sha>` from this checkout until an install resets the
# board, capped at 40 runs. Holds the pipeline lock for the whole loop (not
# per run), so ~/wisekiosk-bench's bench-run.timer backs off rather than
# interleaving with this checkout.
#
#   loop.sh <sha> <summary-file>
#
# Appends one line per run to <summary-file>:
#   <host-ts> run=<i> sha=<sha> exit=<bench test's exit status> record=<its
#   records/<ts> directory, or none> reset=<yes|no>
#
# A run resets iff its target_suite report.jsonl's first setup phase shows a
# capture session ending before capture stopped -- the ordering
# tools/kiosk-install.sh guarantees on a clean run (no `session ended` before
# `capture stopped`).
set -euo pipefail
[ -n "${2:-}" ] || { echo "usage: loop.sh <sha> <summary-file>" >&2; exit 2; }
sha=$1
summary=$2

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

set -a
# shellcheck disable=SC1091
source "$HOME/.config/wisebench/bench.env"
set +a
cd "$HOME/meta-wisekiosk"
bench="$HOME/WiseBenchManager/.venv/bin/bench"
branch=$(git branch --show-current)

# target_suite_record BEFORE AFTER -- the records/<ts> directory that
# appeared between the two `ls records/` snapshots and belongs to
# tests/target_suite, or empty if none did.
target_suite_record() {
    local before=$1 after=$2 d
    comm -13 <(printf '%s\n' "$before" | sort) <(printf '%s\n' "$after" | sort) | while read -r d; do
        [ -f "records/$d/run.json" ] || continue
        jq -e 'select(.command_line | test("target_suite"))' "records/$d/run.json" > /dev/null 2>&1 \
            && printf '%s\n' "records/$d"
    done | tail -1
}

# install_reset RECORD -- true iff RECORD's first setup-phase TestReport's
# captured stderr shows a "session ended" line before its "capture stopped"
# line.
install_reset() {
    local record=$1 text stopped ended
    [ -n "$record" ] && [ -f "$record/report.jsonl" ] || return 1
    text=$(jq -rs '
        [.[] | select(.["$report_type"]=="TestReport" and .when=="setup")] | first |
        (.sections // []) | map(select(.[0]=="Captured stderr setup")) | first | .[1] // ""
    ' "$record/report.jsonl")
    stopped=$(printf '%s' "$text" | grep -n "capture stopped" | head -1 | cut -d: -f1)
    ended=$(printf '%s' "$text" | grep -n "session ended" | head -1 | cut -d: -f1)
    [ -n "$stopped" ] && [ -n "$ended" ] && [ "$ended" -lt "$stopped" ]
}

for i in $(seq 1 40); do
    before_dirs=$(ls -1 records/ 2>/dev/null || true)
    status=0
    "$bench" test "$sha" > /dev/null 2>&1 || status=$?
    git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
    after_dirs=$(ls -1 records/ 2>/dev/null || true)
    record=$(target_suite_record "$before_dirs" "$after_dirs")
    reset=no
    install_reset "$record" && reset=yes
    printf '%s run=%s sha=%s exit=%s record=%s reset=%s\n' \
        "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$i" "$sha" "$status" "${record:-none}" "$reset" \
        >> "$summary"
    [ "$reset" = yes ] && break
done
