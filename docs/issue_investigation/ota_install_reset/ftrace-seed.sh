#!/usr/bin/env bash
# One-off, bench-only (pstore-ftrace spec §4): seeds pstore ftrace itself,
# cloned from sysrq-seed.sh (same lock, boot_id wait, pstore save). Proves
# the zone, the filter, IRQs-masked capture, and survival of a
# watchdog-driven warm reset, via the sysrq panic chain
# (write_sysrq_trigger -> __handle_sysrq -> sysrq_handle_crash -> panic ->
# console_verbose). Recoverable: a kernel panic into the same booted slot
# via echo c > /proc/sysrq-trigger, no install in flight.
#
# A precondition failure (ftrace_size, record_ftrace missing, or a filter
# write/assert failing) is VOID, not FAIL: it means the instrument was
# never live, not that detection/capture failed.
#
# Deletes only /sys/fs/pstore/ftrace-ramoops-0, and only after a
# byte-exact copy is verified by sha256 -- never any other pstore record
# (pstore-ftrace spec Q3).
#   ftrace-seed.sh <outdir> <bench-host> <filter-file>
set -euo pipefail
trap 'echo "ftrace-seed: failed at line $LINENO (exit $?)" >&2' ERR
[ -n "${3:-}" ] || { echo "usage: ftrace-seed.sh <outdir> <bench-host> <filter-file>" >&2; exit 2; }
outdir=$1
bench_host=$2
filter_file=$3
mkdir -p "$outdir"
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 "$bench_host")
seed_names="write_sysrq_trigger __handle_sysrq sysrq_handle_crash panic console_verbose"
anchors="bcm2835_handle_irq bcm2835_time_interrupt irq_exit bcm2835_irq devkmsg_write $seed_names"

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

echo "== boot_id before ==" | tee -a "$outdir/LOG"
boot_before=$("${ssh[@]}" 'cat /proc/sys/kernel/random/boot_id')
echo "$boot_before" | tee -a "$outdir/LOG"

echo "== preconditions ==" | tee -a "$outdir/LOG"
# shellcheck disable=SC2016
ftrace_size=$("${ssh[@]}" 'cat /sys/module/ramoops/parameters/ftrace_size 2>/dev/null') || ftrace_size=""
if [ "$ftrace_size" != "65536" ]; then
    echo "VOID: ftrace_size=$ftrace_size, expected 65536 -- instrument not live" >&2
    exit 1
fi
if ! "${ssh[@]}" '[ -e /sys/kernel/debug/pstore/record_ftrace ]'; then
    echo "VOID: /sys/kernel/debug/pstore/record_ftrace does not exist" >&2
    exit 1
fi
uname_before=$("${ssh[@]}" 'uname -v')
echo "ftrace_size=$ftrace_size uname_before=$uname_before" | tee -a "$outdir/LOG"

echo "== saving pstore read-only before any change ==" | tee -a "$outdir/LOG"
mkdir -p "$outdir/pstore-before"
"${ssh[@]}" 'mount -t pstore -o ro pstore /sys/fs/pstore'
files=$("${ssh[@]}" 'ls -1 /sys/fs/pstore')
echo "pstore files before: $files" | tee -a "$outdir/LOG"
ftrace_sha_remote=""
for f in $files; do
    "${ssh[@]}" "cat /sys/fs/pstore/$f" > "$outdir/pstore-before/$f"
    if [ "$f" = "ftrace-ramoops-0" ]; then
        ftrace_sha_remote=$("${ssh[@]}" 'sha256sum /sys/fs/pstore/ftrace-ramoops-0' | cut -d' ' -f1)
    fi
done
"${ssh[@]}" 'umount /sys/fs/pstore'

if [ -n "$ftrace_sha_remote" ]; then
    ftrace_sha_local=$(sha256sum "$outdir/pstore-before/ftrace-ramoops-0" | cut -d' ' -f1)
    echo "ftrace-ramoops-0 sha256: remote=$ftrace_sha_remote local=$ftrace_sha_local" | tee -a "$outdir/LOG"
    if [ "$ftrace_sha_remote" != "$ftrace_sha_local" ]; then
        echo "VOID: ftrace-ramoops-0 copy is not byte-exact -- refusing to delete it" >&2
        exit 1
    fi
    echo "== deleting only ftrace-ramoops-0, copy verified byte-exact ==" | tee -a "$outdir/LOG"
    "${ssh[@]}" 'mount -t pstore pstore /sys/fs/pstore'
    "${ssh[@]}" 'rm -f /sys/fs/pstore/ftrace-ramoops-0'
    "${ssh[@]}" 'umount /sys/fs/pstore'
else
    echo "no pre-existing ftrace-ramoops-0 to delete" | tee -a "$outdir/LOG"
fi

echo "== setting the filter ==" | tee -a "$outdir/LOG"
# shellcheck disable=SC2016
"${ssh[@]}" ': > /sys/kernel/debug/tracing/set_ftrace_filter'
# Reads $filter_file on fd 3, not stdin: a `done < file` loop with an ssh
# call inside its body has every such call inherit the loop's own
# redirected stdin and consume the rest of the file as its own input, so
# `read` sees EOF after the first line and every glob past the first is
# silently never written. Found by hand-reproducing this exact loop
# against the board (count stalled at 166, one glob's worth, instead of
# growing to 311); confirmed fixed by moving the file read to fd 3.
while IFS= read -r glob <&3; do
    [ -n "$glob" ] || continue
    # shellcheck disable=SC2029
    "${ssh[@]}" "echo '$glob' >> /sys/kernel/debug/tracing/set_ftrace_filter" || {
        echo "VOID: filter write failed for: $glob" >&2
        exit 1
    }
done 3< "$filter_file"
for name in $seed_names; do
    # shellcheck disable=SC2029
    "${ssh[@]}" "echo '$name' >> /sys/kernel/debug/tracing/set_ftrace_filter" || {
        echo "VOID: filter write failed for seed name: $name" >&2
        exit 1
    }
done

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

echo "== arming ==" | tee -a "$outdir/LOG"
"${ssh[@]}" 'echo nop > /sys/kernel/debug/tracing/current_tracer'
"${ssh[@]}" 'echo 1 > /sys/kernel/debug/pstore/record_ftrace'
record_ftrace_readback=$("${ssh[@]}" 'cat /sys/kernel/debug/pstore/record_ftrace')
echo "record_ftrace readback: $record_ftrace_readback" | tee -a "$outdir/LOG"
if [ "$record_ftrace_readback" != "1" ]; then
    echo "VOID: record_ftrace did not read back 1" >&2
    exit 1
fi

sleep 10

echo "== triggering sysrq crash ==" | tee -a "$outdir/LOG"
"${ssh[@]}" 'echo c > /proc/sysrq-trigger' > /dev/null 2>&1 || true

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
    echo "ftrace-seed: board did not answer ssh after 30 tries (5 min)" >&2
    exit 1
fi

boot_after=$("${ssh[@]}" 'cat /proc/sys/kernel/random/boot_id')
uname_after=$("${ssh[@]}" 'uname -v')
echo "== boot_id after == $boot_after  uname_before=$uname_before uname_after=$uname_after ==" | tee -a "$outdir/LOG"
if [ "$boot_after" = "$boot_before" ]; then
    echo "ftrace-seed: boot_id unchanged -- the board did not reboot" >&2
    exit 1
fi
if [ "$uname_before" != "$uname_after" ]; then
    echo "ftrace-seed: uname -v changed ($uname_before -> $uname_after) -- the reading kernel is not the tracing kernel, symbolization is not valid" >&2
    exit 1
fi

echo "== rsts ==" | tee -a "$outdir/LOG"
# shellcheck disable=SC2016
"${ssh[@]}" 'for f in rsts partition tryboot boot-mode; do printf "%s: " $f; hexdump -v -e "4/1 \"%02x\"" /proc/device-tree/chosen/bootloader/$f 2>&1; echo; done' | tee -a "$outdir/LOG"

echo "== mounting pstore read-only, copying ==" | tee -a "$outdir/LOG"
mkdir -p "$outdir/pstore"
"${ssh[@]}" 'mount -t pstore -o ro pstore /sys/fs/pstore'
files=$("${ssh[@]}" 'ls -1 /sys/fs/pstore')
echo "pstore files: $files" | tee -a "$outdir/LOG"
for f in $files; do
    "${ssh[@]}" "cat /sys/fs/pstore/$f" > "$outdir/pstore/$f"
done
"${ssh[@]}" 'umount /sys/fs/pstore'

touch "$outdir/DONE"
echo "ftrace-seed complete" | tee -a "$outdir/LOG"
