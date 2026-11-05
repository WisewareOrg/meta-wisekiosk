#!/usr/bin/env bash
# pstore-ftrace spec (sec 3/sec 5) C2+C3, one armed install: arms the
# production filter plus function_profile_enabled (a live hit-count
# table, for C2's rate) and record_ftrace (the real loop10 mechanism, for
# C3's perturbation check), alongside loop9c's own set_lockup_thresh and
# arm_diagnostics so the comparison against loop9c's healthy runs is
# apples-to-apples except for ftrace. Runs one `bench test <sha>`.
#
# function_profile_enabled's trace_stat/function0 lives in kernel memory,
# not pstore, so it is gone the instant the board reboots -- and RAUC's
# install-then-reboot is one opaque pytest item from this script's side
# (tools/kiosk-install.sh's own install step does not reboot, but the
# target_suite test that calls it also calls the reboot, inside the same
# `bench test` subprocess this script cannot see inside). So C2's count
# is sampled the same way every other live signal in this investigation
# is (hb245, the [stats] stream): a backgrounded ssh poll, host-stamped
# (stamp.py), every 3 s, for the whole install; the last sample before
# the connection drops (the reboot killing it) is the final count. This
# gives a lower-bound-at-worst reading, not an exact one -- reported as
# such.
#
# ftrace-ramoops-0 is saved+sha256-verified+deleted (Q3) both before
# arming (clears any leftover ring) and after the reboot (reads this
# run's own tail, then clears it so loop10.sh starts from an empty ring).
#   ftrace-c2c3.sh <sha> <outdir> <bench-host> <filter-file>
set -euo pipefail
trap 'echo "ftrace-c2c3: failed at line $LINENO (exit $?)" >&2' ERR
[ -n "${4:-}" ] || { echo "usage: ftrace-c2c3.sh <sha> <outdir> <bench-host> <filter-file>" >&2; exit 2; }
sha=$1
outdir=$2
bench_host=$3
filter_file=$4
script_dir="$(cd "$(dirname "$0")" && pwd)"
hb_script="$script_dir/hb245-wdt.sh"
mkdir -p "$outdir"
outdir=$(cd "$outdir" && pwd)
filter_file=$(cd "$(dirname "$filter_file")" && pwd)/$(basename "$filter_file")
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 "$bench_host")
anchors="bcm2835_handle_irq bcm2835_time_interrupt irq_exit bcm2835_irq devkmsg_write"

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

set -a
# shellcheck disable=SC1091
source "$HOME/.config/wisebench/bench.env"
set +a
cd "$HOME/meta-wisekiosk"
bench="$HOME/WiseBenchManager/.venv/bin/bench"
branch=$(git branch --show-current)

# save_and_clear_ftrace_ramoops -- Q3: save pstore, and if ftrace-ramoops-0
# is present, sha256-verify the local copy against the board, then delete
# only that file.
save_and_clear_ftrace_ramoops() {
    local dir=$1
    mkdir -p "$dir"
    "${ssh[@]}" 'mount -t pstore -o ro pstore /sys/fs/pstore'
    local files sha_remote sha_local f
    files=$("${ssh[@]}" 'ls -1 /sys/fs/pstore')
    echo "pstore files: $files" | tee -a "$outdir/LOG"
    sha_remote=""
    for f in $files; do
        "${ssh[@]}" "cat /sys/fs/pstore/$f" > "$dir/$f"
        [ "$f" = "ftrace-ramoops-0" ] && sha_remote=$("${ssh[@]}" 'sha256sum /sys/fs/pstore/ftrace-ramoops-0' | cut -d' ' -f1)
    done
    "${ssh[@]}" 'umount /sys/fs/pstore'
    if [ -n "$sha_remote" ]; then
        sha_local=$(sha256sum "$dir/ftrace-ramoops-0" | cut -d' ' -f1)
        echo "ftrace-ramoops-0 sha256: remote=$sha_remote local=$sha_local" | tee -a "$outdir/LOG"
        if [ "$sha_remote" != "$sha_local" ]; then
            echo "VOID: ftrace-ramoops-0 copy is not byte-exact -- refusing to delete it" >&2
            exit 1
        fi
        "${ssh[@]}" 'mount -t pstore pstore /sys/fs/pstore'
        "${ssh[@]}" 'rm -f /sys/fs/pstore/ftrace-ramoops-0'
        "${ssh[@]}" 'umount /sys/fs/pstore'
        echo "deleted ftrace-ramoops-0, copy verified byte-exact" | tee -a "$outdir/LOG"
    else
        echo "no ftrace-ramoops-0 to delete" | tee -a "$outdir/LOG"
    fi
}

echo "== preconditions ==" | tee -a "$outdir/LOG"
record_ftrace_before=$("${ssh[@]}" 'cat /sys/kernel/debug/pstore/record_ftrace')
if [ "$record_ftrace_before" != "0" ]; then
    echo "VOID: record_ftrace=$record_ftrace_before before start, expected 0" >&2
    exit 1
fi
uname_before=$("${ssh[@]}" 'uname -v')
boot_before=$("${ssh[@]}" 'cat /proc/sys/kernel/random/boot_id')
echo "uname_before=$uname_before boot_before=$boot_before" | tee -a "$outdir/LOG"

echo "== clearing any leftover ftrace-ramoops-0 before arming ==" | tee -a "$outdir/LOG"
save_and_clear_ftrace_ramoops "$outdir/pstore-pre"

echo "== setting the production filter ==" | tee -a "$outdir/LOG"
"${ssh[@]}" ': > /sys/kernel/debug/tracing/set_ftrace_filter'
while IFS= read -r glob <&3; do
    [ -n "$glob" ] || continue
    # shellcheck disable=SC2029
    "${ssh[@]}" "echo '$glob' >> /sys/kernel/debug/tracing/set_ftrace_filter" || {
        echo "VOID: filter write failed for: $glob" >&2
        exit 1
    }
done 3< "$filter_file"
filter_readback=$("${ssh[@]}" 'cat /sys/kernel/debug/tracing/set_ftrace_filter')
echo "$filter_readback" > "$outdir/set_ftrace_filter.txt"
echo "filter entries: $(echo "$filter_readback" | wc -l)" | tee -a "$outdir/LOG"
for anchor in $anchors; do
    if ! grep -qx "$anchor" "$outdir/set_ftrace_filter.txt"; then
        echo "VOID: anchor missing from set_ftrace_filter: $anchor" >&2
        exit 1
    fi
done
echo "all anchors present" | tee -a "$outdir/LOG"
"${ssh[@]}" 'echo nop > /sys/kernel/debug/tracing/current_tracer'

echo "== loop9c's own pre-run diagnostics, so the comparison is apples-to-apples ==" | tee -a "$outdir/LOG"
# shellcheck disable=SC2016
"${ssh[@]}" '
    if [ ! -e /proc/sys/kernel/watchdog_thresh ]; then
        echo "FAIL: kernel.watchdog_thresh does not exist" >&2
        exit 1
    fi
    sysctl -w kernel.watchdog_thresh=1
'
# shellcheck disable=SC2016
"${ssh[@]}" 'for kv in kernel.printk_devkmsg=on kernel.hung_task_timeout_secs=10 kernel.hung_task_check_interval_secs=2 kernel.hung_task_warnings=-1; do sysctl -w "$kv" || echo "sysctl missing or failed: $kv"; done'
"${ssh[@]}" 'cat > /tmp/hb245.sh' < "$hb_script"
"${ssh[@]}" 'chmod +x /tmp/hb245.sh'
"${ssh[@]}" 'setsid nohup sh /tmp/hb245.sh </dev/null >/dev/null 2>&1 &'

echo "== arming: function_profile_enabled (C2) + record_ftrace (C3) ==" | tee -a "$outdir/LOG"
"${ssh[@]}" 'echo 1 > /sys/kernel/debug/tracing/function_profile_enabled'
fpe=$("${ssh[@]}" 'cat /sys/kernel/debug/tracing/function_profile_enabled')
"${ssh[@]}" 'echo 1 > /sys/kernel/debug/pstore/record_ftrace'
rfe=$("${ssh[@]}" 'cat /sys/kernel/debug/pstore/record_ftrace')
ftrace_size=$("${ssh[@]}" 'cat /sys/module/ramoops/parameters/ftrace_size')
echo "function_profile_enabled=$fpe record_ftrace=$rfe ftrace_size=$ftrace_size" | tee -a "$outdir/LOG"
if [ "$fpe" != "1" ] || [ "$rfe" != "1" ]; then
    echo "VOID: arming did not read back 1/1" >&2
    exit 1
fi
arm_epoch=$("${ssh[@]}" 'date +%s.%N')
echo "arm_epoch=$arm_epoch" | tee -a "$outdir/LOG"

echo "== starting the C2 background sampler (host-stamped, every 3s) ==" | tee -a "$outdir/LOG"
"${ssh[@]}" 'while true; do date +%s.%N; cat /sys/kernel/debug/tracing/trace_stat/function0 2>/dev/null; echo ===SAMPLE===; sleep 3; done' \
    2> "$outdir/c2-sampler.err" | python3 "$script_dir/stamp.py" > "$outdir/c2-profile-samples.log" &
sampler_pid=$!

echo "== running bench test $sha ==" | tee -a "$outdir/LOG"
before_dirs=$(ls -1 records/ 2>/dev/null || true)
status=0
"$bench" test "$sha" > "$outdir/bench-test.log" 2>&1 || status=$?
git symbolic-ref -q HEAD > /dev/null || git checkout -q "$branch"
after_dirs=$(ls -1 records/ 2>/dev/null || true)
record=$(comm -13 <(printf '%s\n' "$before_dirs" | sort) <(printf '%s\n' "$after_dirs" | sort) | while read -r d; do
    [ -f "records/$d/run.json" ] || continue
    (jq -e 'select(.command_line | test("target_suite"))' "records/$d/run.json" > /dev/null 2>&1 \
        && printf '%s\n' "records/$d") || true
done | tail -1)
echo "bench test exit=$status record=${record:-none}" | tee -a "$outdir/LOG"

kill "$sampler_pid" 2>/dev/null || true
wait "$sampler_pid" 2>/dev/null || true

# This is a real install: it carries the same ~2.6% reset hazard as any
# other. If this one install hits it, stop instead of treating the run
# as the healthy data point C2/C3 need -- loop9c's own test for it
# (session ended before capture stopped).
reset_hit=no
if [ -n "$record" ] && [ -f "$record/report.jsonl" ]; then
    text=$(jq -rs '
        [.[] | select(.["$report_type"]=="TestReport" and .when=="setup")] | first |
        (.sections // []) | map(select(.[0]=="Captured stderr setup")) | first | .[1] // ""
    ' "$record/report.jsonl")
    stopped_line=$(printf '%s' "$text" | grep -n "capture stopped" | head -1 | cut -d: -f1)
    ended_line=$(printf '%s' "$text" | grep -n "session ended" | head -1 | cut -d: -f1)
    if [ -n "$stopped_line" ] && [ -n "$ended_line" ] && [ "$ended_line" -lt "$stopped_line" ]; then
        reset_hit=yes
    fi
fi
if [ "$status" -ne 0 ] || [ -z "$record" ] || [ "$reset_hit" = "yes" ]; then
    echo "STOP: this armed install did not complete as a clean, healthy run (status=$status record=${record:-none} reset_hit=$reset_hit) -- not reporting C2/C3 numbers from it; escalating instead of treating it as the healthy data point" >&2
    exit 1
fi

echo "== waiting for the board to come back ==" | tee -a "$outdir/LOG"
ok=0
for _ in $(seq 1 30); do
    sleep 10
    if "${ssh[@]}" true 2>/dev/null; then
        ok=1
        break
    fi
done
if [ "$ok" -ne 1 ]; then
    echo "ftrace-c2c3: board did not answer ssh after 30 tries (5 min)" >&2
    exit 1
fi
boot_after=$("${ssh[@]}" 'cat /proc/sys/kernel/random/boot_id')
uname_after=$("${ssh[@]}" 'uname -v')
echo "boot_after=$boot_after uname_after=$uname_after" | tee -a "$outdir/LOG"
if [ "$uname_after" != "$uname_before" ]; then
    echo "ftrace-c2c3: uname -v changed ($uname_before -> $uname_after)" >&2
    exit 1
fi

echo "== reading this run's ftrace tail, then clearing the ring (Q3) ==" | tee -a "$outdir/LOG"
save_and_clear_ftrace_ramoops "$outdir/pstore-post"

if [ -z "$record" ]; then
    echo "VOID: no target_suite record for this bench test" >&2
    exit 1
fi
echo "$record" > "$outdir/record.txt"

touch "$outdir/DONE"
echo "ftrace-c2c3 complete" | tee -a "$outdir/LOG"
