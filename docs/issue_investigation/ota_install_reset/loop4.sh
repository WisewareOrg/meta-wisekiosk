#!/usr/bin/env bash
# Investigation-only reset hunt for #245, batch 4: loop3.sh's structure plus
# one added pre-run diagnostic -- pins cpu0 to the `performance` governor
# (fixed frequency, no DVFS) on the board's current boot before each run,
# testing the fixed-frequency half of upstream raspberrypi/linux#2555's
# Pi Zero instability fix. Uses hb245-freq.sh, which appends the live CPU
# frequency to the heartbeat line. Nothing here ships: no change to
# tools/kiosk-install.sh, the image, or any recipe. Repeats `bench test <sha>`
# from this checkout until an install resets the board, capped at 90 runs.
# Holds the pipeline lock for the whole loop (not per run), so
# ~/wisekiosk-bench's bench-run.timer backs off rather than interleaving.
#
#   loop4.sh <sha> <summary-file> <bench-host>
#
# Appends one line per run to <summary-file>:
#   <host-ts> run=<i> sha=<sha> exit=<bench test's exit status> record=<its
#   records/<ts> directory, or none> reset=<yes|no>
#
# A run resets iff its target_suite report.jsonl's first setup phase shows a
# capture session ending before capture stopped (loop.sh's own check). On
# that run, before the summary line is written or the loop exits, pstore is
# mounted read-only, every file copied byte-exact to that run's own
# records/<ts>/pstore/ directory, and unmounted. Nothing in pstore is ever
# deleted.
#
# The governor step is not optional: if `performance` is not among this
# board's scaling_available_governors, the script stops rather than
# substitute another governor.
set -euo pipefail
[ -n "${3:-}" ] || { echo "usage: loop4.sh <sha> <summary-file> <bench-host>" >&2; exit 2; }
sha=$1
summary=$2
bench_host=$3
hb_script="$(cd "$(dirname "$0")" && pwd)/hb245-freq.sh"

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

# set_governor -- pins cpu0 to the performance governor on the board's
# current boot and logs the readback (scaling_governor, scaling_cur_freq,
# scaling_max_freq). Not optional: stops this script, not just this run, if
# performance is not among scaling_available_governors.
set_governor() {
    # shellcheck disable=SC2016
    "${ssh[@]}" "$bench_host" '
        avail=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors)
        case " $avail " in
            *" performance "*) ;;
            *) echo "FAIL: performance not in scaling_available_governors: $avail" >&2; exit 1 ;;
        esac
        echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
        echo "scaling_governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor) scaling_cur_freq=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq) scaling_max_freq=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq)"
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

for i in $(seq 1 90); do
    set_governor
    arm_diagnostics
    before_dirs=$(ls -1 records/ 2>/dev/null || true)
    status=0
    "$bench" test "$sha" > /dev/null 2>&1 || status=$?
    git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
    after_dirs=$(ls -1 records/ 2>/dev/null || true)
    record=$(target_suite_record "$before_dirs" "$after_dirs")
    reset=no
    install_reset "$record" && reset=yes
    if [ "$reset" = yes ]; then
        save_pstore "$record"
    fi
    printf '%s run=%s sha=%s exit=%s record=%s reset=%s\n' \
        "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$i" "$sha" "$status" "${record:-none}" "$reset" \
        >> "$summary"
    [ "$reset" = yes ] && break
done
