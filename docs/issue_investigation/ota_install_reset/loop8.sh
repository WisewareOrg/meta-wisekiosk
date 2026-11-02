#!/usr/bin/env bash
# Investigation-only reset hunt for #245, batch 8: loop5.sh's diagnostics
# and heartbeat (hung-task sysctls, hb245-wdt.sh) at the image's default
# levers -- mq-deadline scheduler, no bfq; default governor -- plus one
# added pre-run step: arms the soft-lockup detector this commit built into
# the kernel (meta-wisekiosk/recipes-kernel/linux/files/lockup-detect.cfg),
# by setting kernel.watchdog_thresh=3 (a 6s soft-lockup threshold, under
# the 14s hardware watchdog). This ships: the kernel fragment is in the
# main image now, not a diagnostic overlay -- loop8.sh itself ships
# nothing and changes no other config. Repeats `bench test <sha>` from
# this checkout until an install resets the board, capped at 90 runs.
# Holds the pipeline lock for the whole loop (not per run), so
# ~/wisekiosk-bench's bench-run.timer backs off rather than interleaving.
#
#   loop8.sh <sha> <summary-file> <bench-host>
#
# Appends one line per run to <summary-file>:
#   <host-ts> run=<i> sha=<sha> exit=<bench test's exit status> record=<its
#   records/<ts> directory, or none> reset=<yes|no> panic=<yes|no|n/a>
#
# A run resets iff its target_suite report.jsonl's first setup phase shows a
# capture session ending before capture stopped (loop.sh's own check). On
# that run, before the summary line is written or the loop exits, pstore is
# mounted read-only, every file copied byte-exact to that run's own
# records/<ts>/pstore/ directory, and unmounted. Nothing in pstore is ever
# deleted. `panic` records whether that pstore copy holds a
# `dmesg-ramoops-*` file (the detector panicked) or only the console
# record; it is `n/a` on a clean run.
#
# The watchdog_thresh step is not optional: if the sysctl key does not
# exist, the detector is not live and the script stops -- safe to enforce
# from run 1 because a one-off bootstrap install (batch8-bootstrap.sh, not
# part of this loop) already put the detector-enabled kernel on bench
# before this script is ever launched. Checked and set once per run (it
# reverts at that boot's own reboot).
#
# Before each run's pre-run diagnostics, waits for the board to answer ssh
# (it may still be settling after the previous run's reboot): up to 30
# tries, 10 s apart. If it never answers, the loop stops rather than skip
# diagnostics and carry on. An ERR trap names the failing line and exit
# status on any other failure, so a stop is never silent.
set -euo pipefail
trap 'echo "loop8: failed at line $LINENO (exit $?)" >&2' ERR
[ -n "${3:-}" ] || { echo "usage: loop8.sh <sha> <summary-file> <bench-host>" >&2; exit 2; }
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

# set_lockup_thresh -- arms the soft-lockup detector's threshold at 3s
# (6s to panic) on the board's current boot and logs the readback. Not
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
        sysctl -w kernel.watchdog_thresh=3
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
    wait_for_board || { echo "loop8: board did not answer ssh after 30 tries (5 min); stopping before run $i" >&2; break; }
    set_lockup_thresh
    arm_diagnostics
    before_dirs=$(ls -1 records/ 2>/dev/null || true)
    status=0
    "$bench" test "$sha" > /dev/null 2>&1 || status=$?
    git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
    after_dirs=$(ls -1 records/ 2>/dev/null || true)
    record=$(target_suite_record "$before_dirs" "$after_dirs")
    reset=no
    panic=n/a
    install_reset "$record" && reset=yes
    if [ "$reset" = yes ]; then
        save_pstore "$record"
        panic=no
        panic_recorded "$record" && panic=yes
    fi
    printf '%s run=%s sha=%s exit=%s record=%s reset=%s panic=%s\n' \
        "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$i" "$sha" "$status" "${record:-none}" "$reset" "$panic" \
        >> "$summary"
    [ "$reset" = yes ] && break
done
