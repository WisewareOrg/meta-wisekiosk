#!/usr/bin/env bash
# pstore-ftrace spec (sec 3, "Per-run cost checks") C1: per-record cost.
# Filter `read_zero write_null` (the /dev/zero read handler and /dev/null
# write handler), then time `dd if=/dev/zero of=/dev/null bs=1
# count=1000000` -- 1M reads + 1M writes = 2M traced calls when armed.
# Alternates disarmed/armed, 3 runs each; (mean armed - mean disarmed) /
# 2e6 = microseconds per record. No install, no board reset: pure
# per-call-site overhead with the board otherwise idle.
#   ftrace-c1.sh <outdir> <bench-host>
set -euo pipefail
trap 'echo "ftrace-c1: failed at line $LINENO (exit $?)" >&2' ERR
[ -n "${2:-}" ] || { echo "usage: ftrace-c1.sh <outdir> <bench-host>" >&2; exit 2; }
outdir=$1
bench_host=$2
mkdir -p "$outdir"
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 "$bench_host")

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

echo "== preconditions ==" | tee -a "$outdir/LOG"
record_ftrace_before=$("${ssh[@]}" 'cat /sys/kernel/debug/pstore/record_ftrace')
if [ "$record_ftrace_before" != "0" ]; then
    echo "VOID: record_ftrace=$record_ftrace_before before C1 started, expected 0 (disarmed)" >&2
    exit 1
fi

echo "== setting the C1 filter (read_zero write_null) ==" | tee -a "$outdir/LOG"
"${ssh[@]}" ': > /sys/kernel/debug/tracing/set_ftrace_filter; echo read_zero >> /sys/kernel/debug/tracing/set_ftrace_filter; echo write_null >> /sys/kernel/debug/tracing/set_ftrace_filter'
filter_readback=$("${ssh[@]}" 'cat /sys/kernel/debug/tracing/set_ftrace_filter')
echo "$filter_readback" | tee -a "$outdir/LOG"
for name in read_zero write_null; do
    if ! echo "$filter_readback" | grep -qx "$name"; then
        echo "VOID: $name did not resolve in set_ftrace_filter" >&2
        exit 1
    fi
done
"${ssh[@]}" 'echo nop > /sys/kernel/debug/tracing/current_tracer'

# run_dd ARMED -- sets record_ftrace to 0 or 1, runs the dd, and prints
# the real-time seconds (ash's `time` keyword: "real\t0m 0.43s").
run_dd() {
    local armed=$1
    "${ssh[@]}" "echo $armed > /sys/kernel/debug/pstore/record_ftrace"
    "${ssh[@]}" 'time dd if=/dev/zero of=/dev/null bs=1 count=1000000 2>&1' 2>&1 \
        | awk '$1=="real"{min=$2; sec=$3; gsub("m","",min); gsub("s","",sec); print min*60+sec}'
}

echo "== 3 disarmed, 3 armed, alternating ==" | tee -a "$outdir/LOG"
: > "$outdir/c1-runs.txt"
for i in 1 2 3; do
    t=$(run_dd 0)
    echo "run=$i armed=0 real=$t" | tee -a "$outdir/LOG" >> "$outdir/c1-runs.txt"
    t=$(run_dd 1)
    echo "run=$i armed=1 real=$t" | tee -a "$outdir/LOG" >> "$outdir/c1-runs.txt"
done

echo "== disarming, saving+deleting any ftrace-ramoops-0 the dd runs left behind (Q3) ==" | tee -a "$outdir/LOG"
"${ssh[@]}" 'echo 0 > /sys/kernel/debug/pstore/record_ftrace'
"${ssh[@]}" ': > /sys/kernel/debug/tracing/set_ftrace_filter'
mkdir -p "$outdir/pstore-after-c1"
"${ssh[@]}" 'mount -t pstore -o ro pstore /sys/fs/pstore'
files=$("${ssh[@]}" 'ls -1 /sys/fs/pstore')
echo "pstore files after C1: $files" | tee -a "$outdir/LOG"
ftrace_sha_remote=""
for f in $files; do
    "${ssh[@]}" "cat /sys/fs/pstore/$f" > "$outdir/pstore-after-c1/$f"
    if [ "$f" = "ftrace-ramoops-0" ]; then
        ftrace_sha_remote=$("${ssh[@]}" 'sha256sum /sys/fs/pstore/ftrace-ramoops-0' | cut -d' ' -f1)
    fi
done
"${ssh[@]}" 'umount /sys/fs/pstore'
if [ -n "$ftrace_sha_remote" ]; then
    ftrace_sha_local=$(sha256sum "$outdir/pstore-after-c1/ftrace-ramoops-0" | cut -d' ' -f1)
    echo "ftrace-ramoops-0 sha256: remote=$ftrace_sha_remote local=$ftrace_sha_local" | tee -a "$outdir/LOG"
    if [ "$ftrace_sha_remote" != "$ftrace_sha_local" ]; then
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

touch "$outdir/DONE"
echo "ftrace-c1 complete" | tee -a "$outdir/LOG"
