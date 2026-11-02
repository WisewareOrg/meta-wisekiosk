#!/usr/bin/env bash
# One-off, bench-only, owner-authorized: seeds the soft-lockup DETECTION
# half (the sysrq seed only proved panic -> pstore). Starves the
# softlockup touch, which on this non-CONFIG_SMP board is a plain
# system_wq (CFS) kworker -- confirmed in include/linux/stop_machine.h's
# !CONFIG_SMP fallback, stop_one_cpu_nowait() reduces to schedule_work().
# There is no real stop-machine class on this kernel to starve; CFS is
# the actual target, and 6.12's fair-server dl_server independently
# guarantees it ~50ms/s even when the RT group throttle is disabled, so
# both must be turned off, not just one. A CPU-bound SCHED_FIFO-99
# busy loop can then starve it past watchdog_thresh=1's worst-case
# ~2-3.55s detection latency.
#
# Recoverable even if detection fails: the busy loop also starves PID1
# (also SCHED_NORMAL), so systemd stops petting the hardware watchdog,
# which resets the board within its normal 14s regardless.
#   softlockup-seed.sh <outdir> <bench-host>
set -euo pipefail
trap 'echo "softlockup-seed: failed at line $LINENO (exit $?)" >&2' ERR
outdir=$1
bench_host=$2
mkdir -p "$outdir"
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 "$bench_host")

exec {lock_fd}>"$HOME/wisekiosk-bench/records/lock"
flock -x "$lock_fd"

echo "== boot_id before ==" | tee -a "$outdir/LOG"
boot_before=$("${ssh[@]}" 'cat /proc/sys/kernel/random/boot_id')
echo "$boot_before" | tee -a "$outdir/LOG"

echo "== arming: watchdog_thresh=1, rt throttle off, fair server off ==" | tee -a "$outdir/LOG"
# shellcheck disable=SC2016
"${ssh[@]}" '
    if [ ! -e /proc/sys/kernel/watchdog_thresh ]; then
        echo "FAIL: kernel.watchdog_thresh does not exist" >&2
        exit 1
    fi
    sysctl -w kernel.watchdog_thresh=1
    sysctl -w kernel.sched_rt_runtime_us=-1
    echo 0 > /sys/kernel/debug/sched/fair_server/cpu0/runtime
    cat /sys/kernel/debug/sched/fair_server/cpu0/runtime
' | tee -a "$outdir/LOG"

echo "== launching the chrt -f 99 busy loop, backgrounded ==" | tee -a "$outdir/LOG"
# A short client-side timeout: the loop starving CFS can delay the ssh
# session's own wrap-up (also SCHED_NORMAL) indefinitely once the RT
# task is runnable, so this call is expected to time out, not return
# cleanly -- that is not itself a failure signal.
timeout 20 "${ssh[@]}" 'setsid nohup chrt -f 99 sh -c "while true; do :; done" </dev/null >/dev/null 2>&1 & disown; echo launched' \
    >> "$outdir/LOG" 2>&1 || echo "(launch call did not return cleanly within 20s -- expected if the loop is already starving CFS)" | tee -a "$outdir/LOG"

echo "== waiting for the board to come back ==" | tee -a "$outdir/LOG"
ok=0
for _ in $(seq 1 60); do
    sleep 10
    if "${ssh[@]}" true 2>/dev/null; then
        ok=1
        break
    fi
done
if [ "$ok" -ne 1 ]; then
    echo "softlockup-seed: board did not answer ssh after 60 tries (10 min)" >&2
    exit 1
fi

boot_after=$("${ssh[@]}" 'cat /proc/sys/kernel/random/boot_id')
echo "== boot_id after == $boot_after" | tee -a "$outdir/LOG"
if [ "$boot_after" = "$boot_before" ]; then
    echo "softlockup-seed: boot_id unchanged -- the board did not reboot" >&2
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
echo "softlockup-seed complete" | tee -a "$outdir/LOG"
