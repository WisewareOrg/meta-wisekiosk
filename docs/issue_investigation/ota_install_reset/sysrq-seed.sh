#!/usr/bin/env bash
# One-off, bench-only: seeds the panic -> pstore capture path with
# `echo c > /proc/sysrq-trigger` (sysrq_handle_crash -> panic("sysrq
# triggered crash") -> kmsg_dump -> dmesg-ramoops, then the panic=10
# restart). Proves panic-to-pstore capture works; does NOT exercise the
# soft-lockup detector itself. Recoverable: a kernel panic into the same
# booted slot, no install in flight, no /boot/slot/keyring touch.
#   sysrq-seed.sh <outdir> <bench-host>
set -euo pipefail
trap 'echo "sysrq-seed: failed at line $LINENO (exit $?)" >&2' ERR
[ -n "${2:-}" ] || { echo "usage: sysrq-seed.sh <outdir> <bench-host>" >&2; exit 2; }
outdir=$1
bench_host=$2
mkdir -p "$outdir"
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 "$bench_host")

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

echo "== boot_id before ==" | tee -a "$outdir/LOG"
boot_before=$("${ssh[@]}" 'cat /proc/sys/kernel/random/boot_id')
echo "$boot_before" | tee -a "$outdir/LOG"

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
    echo "sysrq-seed: board did not answer ssh after 30 tries (5 min)" >&2
    exit 1
fi

boot_after=$("${ssh[@]}" 'cat /proc/sys/kernel/random/boot_id')
echo "== boot_id after == $boot_after" | tee -a "$outdir/LOG"
if [ "$boot_after" = "$boot_before" ]; then
    echo "sysrq-seed: boot_id unchanged -- the board did not reboot" >&2
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
echo "sysrq-seed complete" | tee -a "$outdir/LOG"
