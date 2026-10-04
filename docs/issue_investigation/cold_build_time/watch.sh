#!/bin/bash
# Samples memory pressure and webkitgtk3's do_compile progress every 60s into
# watch.log, and flags a restart trigger: active thrash (PSI full avg300 > 10
# for 15 consecutive samples) or an OOM-kill. Elapsed do_compile time is
# logged but never triggers PROBLEM on its own. Exits once run.done exists.
# Launched detached by run-cold-build.sh; not meant to be run by hand.
set -euo pipefail

REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$REPO"

LOG=build/coldbuild/watch.log
mkdir -p build/coldbuild

psi_streak=0
oom_flagged=0
killed_flagged=0

newest_buildstats() {
    find build/coldbuild -mindepth 3 -maxdepth 3 -type d -path '*/buildstats/*' 2>/dev/null \
        | sort | tail -1 || true
}

while :; do
    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

    psi=$( { awk -F'avg300=' '/^full /{split($2,a," "); print a[1]; exit}' /proc/pressure/memory; } 2>/dev/null || true)
    [ -z "$psi" ] && psi="?"
    mem_avail=$( { awk '/^MemAvailable:/{print $2; exit}' /proc/meminfo; } 2>/dev/null || true)
    swap_free=$( { awk '/^SwapFree:/{print $2; exit}' /proc/meminfo; } 2>/dev/null || true)

    bsdir=$(newest_buildstats)
    compile_file=""
    if [ -n "$bsdir" ]; then
        compile_file=$(find "$bsdir" -mindepth 2 -maxdepth 2 -type f -name do_compile \
            -path '*/webkitgtk3-*/do_compile' 2>/dev/null | head -1 || true)
    fi

    running=0
    elapsed="-"
    if [ -n "$compile_file" ] && [ -f "$compile_file" ] && ! grep -q '^Ended:' "$compile_file"; then
        running=1
        started=$(awk -F': ' '/^Started:/{print $2; exit}' "$compile_file" 2>/dev/null || true)
        if [ -n "$started" ]; then
            elapsed=$(( $(date +%s) - ${started%.*} ))
        fi
    fi

    echo "$ts psi_full_avg300=$psi mem_available_kb=${mem_avail:-?} swap_free_kb=${swap_free:-?} webkit_do_compile_elapsed_s=$elapsed" >> "$LOG"

    if [ "$running" -eq 1 ]; then
        high=0
        case "$psi" in
            ''|'?') ;;
            *) high=$(awk -v p="$psi" 'BEGIN{print (p+0>10)?1:0}') ;;
        esac
        if [ "$high" -eq 1 ]; then
            psi_streak=$((psi_streak + 1))
        else
            psi_streak=0
        fi
        if [ "$psi_streak" -eq 15 ]; then
            echo "$ts PROBLEM psi full avg300 > 10 for 15 consecutive samples" >> "$LOG"
        fi
    else
        psi_streak=0
    fi

    if [ "$oom_flagged" -eq 0 ] && dmesg 2>/dev/null | grep -qi 'killed process\|out of memory'; then
        echo "$ts PROBLEM OOM kill seen in dmesg" >> "$LOG"
        oom_flagged=1
    fi
    if [ "$killed_flagged" -eq 0 ] && [ -f build/coldbuild/run.log ] && grep -q 'Killed' build/coldbuild/run.log; then
        echo "$ts PROBLEM 'Killed' seen in run.log" >> "$LOG"
        killed_flagged=1
    fi

    if [ -f build/coldbuild/run.done ]; then
        echo "$ts WATCH-END" >> "$LOG"
        exit 0
    fi
    sleep 60
done
