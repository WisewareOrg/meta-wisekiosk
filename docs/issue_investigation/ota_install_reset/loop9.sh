#!/usr/bin/env bash
# Investigation-only reset hunt for #245, batch 9: loop8.sh with the one
# change reset 7 motivated -- kernel.watchdog_thresh=1 (a 2s soft-lockup
# threshold) instead of 3. At thresh=1 the detector's own worst-case
# latency after a stop is ~3.6 s (sample period 0.4 s, report at
# touch + up to 3.2 s), inside the ~6.3 s minimum the 14 s hardware
# watchdog gives after any pet-cycle phase, with ~2.7 s of margin at
# every phase -- unlike thresh=3, which reset 7 showed could lose the
# race. Everything else is unchanged: same diagnostics and heartbeat
# (hung-task sysctls, hb245-wdt.sh), same default mq-deadline scheduler
# and governor, same loop6/7/8 hardening (ERR trap, wait_for_board).
# This ships nothing new: the kernel fragment already ships; loop9.sh
# only changes a runtime sysctl this investigation controls.
#
#   loop9.sh <sha> <summary-file> <bench-host>
#
# Appends one line per run to <summary-file>:
#   <host-ts> run=<i> sha=<sha> exit=<bench test's exit status> record=<its
#   records/<ts> directory, or none> reset=<yes|no> panic=<yes|no>
#
# A run resets iff its target_suite report.jsonl's first setup phase shows a
# capture session ending before capture stopped (loop.sh's own check).
#
# At this threshold a false soft-lockup panic (the touch is an ordinary
# SCHED_NORMAL kworker on this UP board, so CPU starvation alone can trip
# it) is itself data, not noise: pstore is mounted read-only, copied
# byte-exact into that run's own records/<ts>/pstore/ directory, and
# unmounted -- on EVERY run, not only a reset -- and `panic` records
# whether a dmesg-ramoops-* file (the detector fired) is present. The loop
# stops on `reset=yes` OR `panic=yes`, treating a clean-install false
# panic as a stop-and-capture event exactly like a reset, since the owner
# needs to see it before any more runs land on top of it. Nothing in
# pstore is ever deleted.
#
# The watchdog_thresh step is not optional: if the sysctl key does not
# exist, the detector is not live and the script stops.
#
# Before each run's pre-run diagnostics, waits for the board to answer ssh
# (it may still be settling after the previous run's reboot): up to 30
# tries, 10 s apart. If it never answers, the loop stops rather than skip
# diagnostics and carry on. An ERR trap names the failing line and exit
# status on any other failure, so a stop is never silent.
set -euo pipefail
trap 'echo "loop9: failed at line $LINENO (exit $?)" >&2' ERR
[ -n "${3:-}" ] || { echo "usage: loop9.sh <sha> <summary-file> <bench-host>" >&2; exit 2; }
sha=$1
summary=$2
bench_host=$3
hb_script="$(cd "$(dirname "$0")" && pwd)/hb245-wdt.sh"

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

set -a
# shellcheck disable=SC1091
source "$HOME/.config/wisebench/bench.env"
set +a
cd "$HOME/meta-wisekiosk"
bench="$HOME/WiseBenchManager/.venv/bin/bench"
branch=$(git branch --show-current)
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)

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

# wait_for_board -- retries a trivial ssh every 10 s, up to 30 tries (5 min),
# until the board answers. True once it does; false (stderr logged by the
# caller) if it never does in that window.
wait_for_board() {
    local i
    for i in $(seq 1 30); do
        "${ssh[@]}" "$bench_host" true && return 0
        sleep 10
    done
    return 1
}

# set_lockup_thresh -- arms the soft-lockup detector's threshold at 1s
# (2s to panic) on the board's current boot and logs the readback. Not
# optional: stops this script, not just this run, if kernel.watchdog_thresh
# does not exist -- the detector is not compiled into whatever kernel is
# currently booted.
set_lockup_thresh() {
    # shellcheck disable=SC2016
    "${ssh[@]}" "$bench_host" '
        if [ ! -e /proc/sys/kernel/watchdog_thresh ]; then
            echo "FAIL: kernel.watchdog_thresh does not exist -- the soft-lockup detector is not live" >&2
            exit 1
        fi
        sysctl -w kernel.watchdog_thresh=1
    '
}

# arm_diagnostics -- runtime-only hung-task logging and the heartbeat, on
# the board's current boot. Reverts at that boot's own reboot; a missing
# sysctl key is logged and skipped, not fatal.
arm_diagnostics() {
    # shellcheck disable=SC2016
    "${ssh[@]}" "$bench_host" 'for kv in kernel.printk_devkmsg=on kernel.hung_task_timeout_secs=10 kernel.hung_task_check_interval_secs=2 kernel.hung_task_warnings=-1; do sysctl -w "$kv" || echo "sysctl missing or failed: $kv"; done'
    "${ssh[@]}" "$bench_host" 'cat > /tmp/hb245.sh' < "$hb_script"
    "${ssh[@]}" "$bench_host" 'chmod +x /tmp/hb245.sh'
    "${ssh[@]}" "$bench_host" 'setsid nohup sh /tmp/hb245.sh </dev/null >/dev/null 2>&1 &'
}

# save_pstore RECORD -- mounts pstore read-only, copies every file
# byte-exact into RECORD/pstore/, unmounts. Never deletes a pstore file.
# Called on every run, not only a reset, so a false panic on an otherwise
# clean install is still captured.
save_pstore() {
    local record=$1 f files
    mkdir -p "$record/pstore"
    "${ssh[@]}" "$bench_host" 'mount -t pstore -o ro pstore /sys/fs/pstore' || true
    files=$("${ssh[@]}" "$bench_host" 'ls -1 /sys/fs/pstore') || files=""
    for f in $files; do
        "${ssh[@]}" "$bench_host" "cat /sys/fs/pstore/$f" > "$record/pstore/$f"
    done
    "${ssh[@]}" "$bench_host" 'umount /sys/fs/pstore' || true
}

# panic_recorded RECORD -- true iff RECORD/pstore/ holds a dmesg-ramoops-*
# file (the soft-lockup detector panicked), vs. only the console record.
panic_recorded() {
    local record=$1
    ls "$record"/pstore/dmesg-ramoops-* > /dev/null 2>&1
}

for i in $(seq 1 90); do
    wait_for_board || { echo "loop9: board did not answer ssh after 30 tries (5 min); stopping before run $i" >&2; break; }
    set_lockup_thresh
    arm_diagnostics
    before_dirs=$(ls -1 records/ 2>/dev/null || true)
    status=0
    "$bench" test "$sha" > /dev/null 2>&1 || status=$?
    git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
    after_dirs=$(ls -1 records/ 2>/dev/null || true)
    record=$(target_suite_record "$before_dirs" "$after_dirs")
    reset=no
    install_reset "$record" && reset=yes
    panic=no
    if [ -n "$record" ]; then
        save_pstore "$record"
        panic_recorded "$record" && panic=yes
    fi
    printf '%s run=%s sha=%s exit=%s record=%s reset=%s panic=%s\n' \
        "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$i" "$sha" "$status" "${record:-none}" "$reset" "$panic" \
        >> "$summary"
    { [ "$reset" = yes ] || [ "$panic" = yes ]; } && break
done
