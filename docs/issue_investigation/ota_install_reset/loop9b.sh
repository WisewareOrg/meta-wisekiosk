#!/usr/bin/env bash
# Investigation-only reset hunt for #245, batch 9 (attempt 2): loop9.sh
# with one fix -- loop9's own run 1 stopped on a false panic=yes, because
# its detection was presence-only (any dmesg-ramoops-* file) and ramoops
# records survive a warm reboot until unlinked, which this investigation
# never does. The batch-8 sysrq-seed's dmesg-ramoops-0 was still on the
# board and was mistaken for a new panic.
#
# Fixed here: panic detection compares each dmesg-ramoops-* file's sha256
# against a reference manifest, captured from the board once at loop
# start (before run 1, so a pre-existing record like the seed's is in the
# baseline from the outset) and replaced with the current run's manifest
# after every run. `panic=yes` iff a dmesg-ramoops-* file is new (absent
# from the reference) or its sha256 changed since the reference -- never
# for a file that was already there, unchanged. pstore is still never
# deleted; this changes only how a *record* already captured is read.
#
# Otherwise identical to loop9.sh: watchdog_thresh=1, loop8.sh's
# diagnostics, heartbeat, scheduler/governor defaults, and the
# loop6/7/8/9 hardening (ERR trap, wait_for_board). Mounts and copies
# pstore after every run, not only a reset, and stops on `reset=yes` OR
# `panic=yes`.
#
#   loop9b.sh <sha> <summary-file> <bench-host>
#
# Appends one line per run to <summary-file>:
#   <host-ts> run=<i> sha=<sha> exit=<bench test's exit status> record=<its
#   records/<ts> directory, or none> reset=<yes|no> panic=<yes|no>
#
# A run resets iff its target_suite report.jsonl's first setup phase shows a
# capture session ending before capture stopped (loop.sh's own check).
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
trap 'echo "loop9b: failed at line $LINENO (exit $?)" >&2' ERR
[ -n "${3:-}" ] || { echo "usage: loop9b.sh <sha> <summary-file> <bench-host>" >&2; exit 2; }
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

# pstore_manifest DIR -- prints "sha256  filename" for every file in
# DIR/pstore/ (sorted by filename), or nothing if DIR/pstore doesn't
# exist or is empty. Read-only; never touches the board -- it reads
# files save_pstore already copied locally.
pstore_manifest() {
    local dir=$1
    [ -d "$dir/pstore" ] || return 0
    (cd "$dir/pstore" && sha256sum -- * 2>/dev/null | sort -k2) || true
}

# panic_recorded RECORD BASELINE -- true iff RECORD/pstore/ holds a
# dmesg-ramoops-* file whose sha256 is new or changed relative to
# BASELINE (a pstore_manifest-format file). A file present in BASELINE
# with the same sha256 is a carried-over record, not a new panic, and is
# never flagged.
panic_recorded() {
    local record=$1 baseline=$2 f sha prev
    for f in "$record"/pstore/dmesg-ramoops-*; do
        [ -e "$f" ] || continue
        sha=$(sha256sum -- "$f" | cut -d' ' -f1)
        prev=$(awk -v n="$(basename "$f")" '$2==n{print $1}' "$baseline")
        [ "$sha" != "$prev" ] && return 0
    done
    return 1
}

baseline_dir=$(mktemp -d)
baseline_file=$(mktemp)
trap 'rm -rf "$baseline_dir" "$baseline_file"' EXIT

# Seed the baseline from the board's pstore state before run 1, under the
# lock, so a pre-existing record (like the sysrq seed's) is never
# mistaken for a new panic.
save_pstore "$baseline_dir"
pstore_manifest "$baseline_dir" > "$baseline_file"

for i in $(seq 1 90); do
    wait_for_board || { echo "loop9b: board did not answer ssh after 30 tries (5 min); stopping before run $i" >&2; break; }
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
        panic_recorded "$record" "$baseline_file" && panic=yes
        pstore_manifest "$record" > "$baseline_file"
    fi
    printf '%s run=%s sha=%s exit=%s record=%s reset=%s panic=%s\n' \
        "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$i" "$sha" "$status" "${record:-none}" "$reset" "$panic" \
        >> "$summary"
    { [ "$reset" = yes ] || [ "$panic" = yes ]; } && break
done
