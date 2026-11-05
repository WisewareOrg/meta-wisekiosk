#!/usr/bin/env bash
# Investigation-only reset hunt for #245, batch 10: loop9c.sh plus the
# pstore-ftrace instrument (pstore-ftrace spec sec 5). Every run arms the
# production filter and record_ftrace right after arm_diagnostics and
# before the install (arm_ftrace), and attempts to disarm record_ftrace
# right after bench test returns (disarm_ftrace) -- which is a no-op in
# practice: bench test's target_suite test reboots the board itself,
# inside the one opaque subprocess call this script makes, so by the
# time control returns here the board has already rebooted onto a new
# boot where record_ftrace reverts to 0 on its own (pstore-ftrace spec
# sec 2, "both settings revert at reboot"). disarm_ftrace is kept anyway
# because it is harmless and is exactly the command the spec names; it
# just cannot land before that reboot from an external wrapper around an
# opaque `bench test`, only after. This does not affect catching a reset
# (which happens mid-install, before any clean reboot is reached) --
# only the "healthy tail reference" the spec describes for a clean run's
# own ring content.
#
# On a run that produces a target_suite record, the per-run ftrace tail
# (ftrace_tail.py tail) is saved beside the record always, so a clean
# run's own healthy reference is on hand for comparison when a later run
# resets. ftrace-ramoops-0 is deleted after being copied+sha256-verified
# (Q3) at both arm_ftrace (clearing any leftover ring) and after each
# run's save_pstore (so the next run starts from an empty ring);
# console-ramoops-0 and dmesg-ramoops-0 are never deleted.
#
# Otherwise identical to loop9c.sh: watchdog_thresh=1, loop8.sh's
# diagnostics, heartbeat, panic detection by sha256 against a reference
# manifest, voided-run handling, consecutive-voided stop, wait_for_board.
# Pre-committed cap: 114 (pstore-ftrace spec Q8), stop rule unchanged
# from loop9c otherwise (also stops on 3 consecutive voided runs).
#
#   loop10.sh <sha> <summary-file> <bench-host> <filter-file>
#
# Appends one line per run to <summary-file>:
#   <host-ts> run=<i> sha=<sha> exit=<bench test's exit status> record=<its
#   records/<ts> directory, or none> reset=<yes|no> panic=<yes|no>
#   voided=<yes|no>
set -euo pipefail
trap 'echo "loop10: failed at line $LINENO (exit $?)" >&2' ERR
[ -n "${4:-}" ] || { echo "usage: loop10.sh <sha> <summary-file> <bench-host> <filter-file>" >&2; exit 2; }
sha=$1
summary=$2
bench_host=$3
filter_file=$4
script_dir="$(cd "$(dirname "$0")" && pwd)"
hb_script="$script_dir/hb245-wdt.sh"
filter_file=$(cd "$(dirname "$filter_file")" && pwd)/$(basename "$filter_file")
cap=114
ftrace_anchors="bcm2835_handle_irq bcm2835_time_interrupt irq_exit bcm2835_irq devkmsg_write"

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

# target_suite_record BEFORE AFTER (loop9c.sh, unchanged).
target_suite_record() {
    local before=$1 after=$2 d
    comm -13 <(printf '%s\n' "$before" | sort) <(printf '%s\n' "$after" | sort) | while read -r d; do
        [ -f "records/$d/run.json" ] || continue
        (jq -e 'select(.command_line | test("target_suite"))' "records/$d/run.json" > /dev/null 2>&1 \
            && printf '%s\n' "records/$d") || true
    done | tail -1
}

# install_reset RECORD (loop9c.sh, unchanged).
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

# wait_for_board (loop9c.sh, unchanged).
wait_for_board() {
    local i
    for i in $(seq 1 30); do
        "${ssh[@]}" "$bench_host" true && return 0
        sleep 10
    done
    return 1
}

# set_lockup_thresh (loop9c.sh, unchanged).
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

# arm_diagnostics (loop9c.sh, unchanged).
arm_diagnostics() {
    # shellcheck disable=SC2016
    "${ssh[@]}" "$bench_host" 'for kv in kernel.printk_devkmsg=on kernel.hung_task_timeout_secs=10 kernel.hung_task_check_interval_secs=2 kernel.hung_task_warnings=-1; do sysctl -w "$kv" || echo "sysctl missing or failed: $kv"; done'
    "${ssh[@]}" "$bench_host" 'cat > /tmp/hb245.sh' < "$hb_script"
    "${ssh[@]}" "$bench_host" 'chmod +x /tmp/hb245.sh'
    "${ssh[@]}" "$bench_host" 'setsid nohup sh /tmp/hb245.sh </dev/null >/dev/null 2>&1 &'
}

# save_pstore RECORD (loop9c.sh, unchanged: never deletes).
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

# pstore_manifest DIR (loop9c.sh, unchanged).
pstore_manifest() {
    local dir=$1
    [ -d "$dir/pstore" ] || return 0
    (cd "$dir/pstore" && sha256sum -- * 2>/dev/null | sort -k2) || true
}

# panic_recorded RECORD BASELINE (loop9c.sh, unchanged).
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

# delete_ftrace_ramoops DIR -- Q3: if DIR/pstore/ftrace-ramoops-0 exists
# (already copied there by save_pstore), sha256-verify it against the
# board, then delete only that file. DIR/pstore must already be
# populated by save_pstore; this never re-copies.
#
# save_pstore always unmounts pstore before returning, so the sha256 has
# to be read inside a fresh mount of its own -- not a second call against
# an already-unmounted /sys/fs/pstore, which is what the first version of
# this function did (sha_remote came back empty every time, read as "not
# byte-exact" and voiding every run after the first). Mounts read-write
# once, since a match deletes in the same mount; ftrace-seed.sh avoids
# this by reading the sha inline, in the single mount save_pstore already
# holds open, before it unmounts.
delete_ftrace_ramoops() {
    local dir=$1 sha_local sha_remote
    [ -f "$dir/pstore/ftrace-ramoops-0" ] || return 0
    sha_local=$(sha256sum "$dir/pstore/ftrace-ramoops-0" | cut -d' ' -f1)
    "${ssh[@]}" "$bench_host" 'mount -t pstore pstore /sys/fs/pstore'
    sha_remote=$("${ssh[@]}" "$bench_host" 'sha256sum /sys/fs/pstore/ftrace-ramoops-0 2>/dev/null' | cut -d' ' -f1)
    if [ -z "$sha_remote" ] || [ "$sha_remote" != "$sha_local" ]; then
        "${ssh[@]}" "$bench_host" 'umount /sys/fs/pstore' || true
        echo "loop10: ftrace-ramoops-0 copy is not byte-exact against the board -- refusing to delete it" >&2
        return 1
    fi
    "${ssh[@]}" "$bench_host" 'rm -f /sys/fs/pstore/ftrace-ramoops-0'
    "${ssh[@]}" "$bench_host" 'umount /sys/fs/pstore'
}

# arm_ftrace -- pstore-ftrace spec sec 5. Clears any leftover ring,
# writes the production filter, asserts the anchors, arms record_ftrace.
# Logs filter/uname/ftrace_size/boot_id to arm.log. A precondition
# failure voids the run before the install.
arm_ftrace() {
    local run_i="$1" clear_dir="$2"
    mkdir -p "$clear_dir/pstore"
    "${ssh[@]}" "$bench_host" 'mount -t pstore -o ro pstore /sys/fs/pstore' || true
    local files f
    files=$("${ssh[@]}" "$bench_host" 'ls -1 /sys/fs/pstore') || files=""
    for f in $files; do
        "${ssh[@]}" "$bench_host" "cat /sys/fs/pstore/$f" > "$clear_dir/pstore/$f"
    done
    "${ssh[@]}" "$bench_host" 'umount /sys/fs/pstore' || true
    delete_ftrace_ramoops "$clear_dir" || return 1

    "${ssh[@]}" "$bench_host" ': > /sys/kernel/debug/tracing/set_ftrace_filter'
    while IFS= read -r glob <&3; do
        [ -n "$glob" ] || continue
        # shellcheck disable=SC2029
        "${ssh[@]}" "$bench_host" "echo '$glob' >> /sys/kernel/debug/tracing/set_ftrace_filter" || return 1
    done 3< "$filter_file"
    local readback
    readback=$("${ssh[@]}" "$bench_host" 'cat /sys/kernel/debug/tracing/set_ftrace_filter')
    local anchor
    for anchor in $ftrace_anchors; do
        echo "$readback" | grep -qx "$anchor" || return 1
    done
    "${ssh[@]}" "$bench_host" 'echo nop > /sys/kernel/debug/tracing/current_tracer'
    "${ssh[@]}" "$bench_host" 'echo 1 > /sys/kernel/debug/pstore/record_ftrace'
    local rfe
    rfe=$("${ssh[@]}" "$bench_host" 'cat /sys/kernel/debug/pstore/record_ftrace')
    [ "$rfe" = "1" ] || return 1
    {
        echo "=== run $run_i arm_ftrace $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
        echo "uname: $("${ssh[@]}" "$bench_host" 'uname -v')"
        echo "ftrace_size: $("${ssh[@]}" "$bench_host" 'cat /sys/module/ramoops/parameters/ftrace_size')"
        echo "record_ftrace: $rfe"
        echo "boot_id: $("${ssh[@]}" "$bench_host" 'cat /proc/sys/kernel/random/boot_id')"
        echo "filter entries: $(echo "$readback" | wc -l)"
    } >> "$arm_log"
}

# disarm_ftrace -- see the header comment: a no-op in practice (the
# board has already rebooted by the time bench test returns, and the
# new boot's record_ftrace already reverted to 0), kept because it is
# harmless and is the literal command the spec names.
disarm_ftrace() {
    "${ssh[@]}" "$bench_host" 'echo 0 > /sys/kernel/debug/pstore/record_ftrace' 2>/dev/null || true
}

baseline_dir=$(mktemp -d)
baseline_file=$(mktemp)
arm_log="$(dirname "$summary")/ftrace-arm.log"
trap 'rm -rf "$baseline_dir" "$baseline_file"' EXIT

save_pstore "$baseline_dir"
pstore_manifest "$baseline_dir" > "$baseline_file"

consecutive_voided=0
for i in $(seq 1 "$cap"); do
    wait_for_board || { echo "loop10: board did not answer ssh after 30 tries (5 min); stopping before run $i" >&2; break; }
    set_lockup_thresh
    arm_diagnostics
    arm_dir=$(mktemp -d)
    if ! arm_ftrace "$i" "$arm_dir"; then
        echo "loop10: arm_ftrace failed for run $i -- voiding before install" >&2
        rm -rf "$arm_dir"
        printf '%s run=%s sha=%s exit=void record=none reset=no panic=no voided=yes\n' \
            "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$i" "$sha" >> "$summary"
        consecutive_voided=$((consecutive_voided + 1))
        [ "$consecutive_voided" -ge 3 ] && { echo "loop10: 3 consecutive voided runs, stopping" >&2; break; }
        continue
    fi
    rm -rf "$arm_dir"

    before_dirs=$(ls -1 records/ 2>/dev/null || true)
    status=0
    "$bench" test "$sha" > /dev/null 2>&1 || status=$?
    disarm_ftrace
    git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
    after_dirs=$(ls -1 records/ 2>/dev/null || true)
    record=$(target_suite_record "$before_dirs" "$after_dirs")
    reset=no
    panic=no
    voided=no
    if [ -n "$record" ]; then
        consecutive_voided=0
        install_reset "$record" && reset=yes
        save_pstore "$record"
        panic_recorded "$record" "$baseline_file" && panic=yes
        pstore_manifest "$record" > "$baseline_file"
        if [ -f "$record/pstore/ftrace-ramoops-0" ]; then
            python3 "$script_dir/ftrace_tail.py" tail "$record/pstore/ftrace-ramoops-0" 200 \
                > "$record/ftrace-tail.txt" 2>&1 || true
            delete_ftrace_ramoops "$record" || true
        fi
    else
        voided=yes
        consecutive_voided=$((consecutive_voided + 1))
    fi
    printf '%s run=%s sha=%s exit=%s record=%s reset=%s panic=%s voided=%s\n' \
        "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$i" "$sha" "$status" "${record:-none}" "$reset" "$panic" "$voided" \
        >> "$summary"
    if [ "$voided" = "no" ]; then
        consecutive_voided=0
    elif [ "$consecutive_voided" -ge 3 ]; then
        echo "loop10: 3 consecutive voided runs, stopping" >&2
        break
    fi
    if [ "$reset" = "yes" ] || [ "$panic" = "yes" ]; then
        echo "loop10: reset/panic at run $i, stopping" >&2
        break
    fi
done
