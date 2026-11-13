#!/usr/bin/env bash
# Install a staged RAUC bundle over ssh and show slot state. Does NOT reboot
# -- inspect `rauc status` first, then `just kiosk-reboot`.
#
#   tools/kiosk-install.sh root@<host>
#   tools/kiosk-install.sh --check-only <before> <after>
#
# Checks, in order: the reproducibility gate against the tree containing this
# script, regardless of the caller's working directory (--tree: what installs
# is already on the device); the device clock's skew from the host (reported,
# never set -- a cold clock after a fresh slot's first boot is the documented
# cause of a "certificate is not yet valid" refusal below, see #31); the
# bundle's signature against the device keyring (`rauc info`); and, after
# `rauc install`, that BOOT_ORDER now leads with the slot that was NOT booted
# before, with that slot's *_LEFT counter reset above 0 (target_activated).
#
# During `rauc install` it streams the board's kernel log, journal and
# once-a-second memory/load/SD/undervoltage stats to the console, timestamped
# on this host, and arms two kernel recorders that survive a reset: the
# soft-lockup detector at kernel.watchdog_thresh=1 and the pstore ftrace zone
# over the functions in kiosk-install-ftrace-filter.txt. Arming deletes any
# dmesg and ftrace records already in pstore; disarming restores the threshold
# and empties the filter. The install's session ends after 30 s without an
# answer from the board. If it fails and the board answers again with a new
# boot_id, the board's pstore is printed into the same capture.
#
# --check-only BEFORE AFTER runs target_activated directly against two
# fw_printenv/rauc-status blocks, with no ssh and no device.
#
# Exit: 0 installed and the target slot activated, or --check-only passed;
# 1 the gate failed, the bundle did not verify, the target slot did not
# activate, or --check-only failed; 2 no host given. An ssh or rauc command
# that fails outright exits with that command's own status (e.g. 255).
set -euo pipefail

usage() {
    awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
}

# target_activated BEFORE AFTER -- true if AFTER shows the slot not booted in
# BEFORE now leading BOOT_ORDER with its *_LEFT counter reset above 0.
target_activated() {
    local before=$1 after=$2 prev target new_order target_left
    prev=$(sed -n 's/.*Booted from: rootfs\.[0-9] (\(.\)).*/\1/p' <<<"$before")
    case "$prev" in
        A) target=B ;;
        B) target=A ;;
        *) return 1 ;;
    esac
    new_order=$(sed -n 's/^BOOT_ORDER=//p' <<<"$after")
    target_left=$(sed -n "s/^BOOT_${target}_LEFT=//p" <<<"$after")
    [[ "$new_order" == "$target"* ]] && [ "${target_left:-0}" -gt 0 ]
}

ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
host=
prev_thresh=
capture_pids=()

# Single-quoted throughout: every $ below is the remote busybox shell's.
# shellcheck disable=SC2016
stats_cmd='h=; for d in /sys/class/hwmon/hwmon*; do [ "$(cat "$d"/name 2>/dev/null)" = rpi_volt ] && h="$d"; done; while true; do m=; for f in MemFree Dirty Writeback; do set -- $(grep "^$f:" /proc/meminfo); m="$m$1$2 "; done; set -- $(cat /proc/loadavg); l="load=$1 $2 $3"; set -- $(cat /sys/block/mmcblk0/stat); k="mmc=$*"; u=$(cat "$h/in0_lcrit_alarm"); echo "$m$l $k uv=$u"; sleep 1; done'

# Reads the ftrace filter on stdin. Each step reports its own failure: an
# unarmed recorder never stops the install.
# shellcheck disable=SC2016
arm_cmd='grep -q " /sys/fs/pstore " /proc/mounts || mount -t pstore pstore /sys/fs/pstore || echo "pstore did not mount"
rm -f /sys/fs/pstore/dmesg-ramoops-* /sys/fs/pstore/ftrace-ramoops-0
r=/sys/kernel/debug/pstore/record_ftrace
f=/sys/kernel/tracing/set_ftrace_filter
if [ -e $r ]; then
    : > $f
    while read -r g; do [ -n "$g" ] && { echo "$g" >> $f || echo "ftrace filter rejected: $g"; }; done
    echo nop > /sys/kernel/tracing/current_tracer
    echo 1 > $r || echo "pstore ftrace not armed"
else
    echo "pstore ftrace not armed: no $r"
fi
sysctl -w kernel.watchdog_thresh=1 || echo "soft-lockup threshold not set"
echo "armed: record_ftrace=$(cat $r) filter_entries=$(wc -l < $f) watchdog_thresh=$(cat /proc/sys/kernel/watchdog_thresh) softlockup_panic=$(cat /proc/sys/kernel/softlockup_panic)"'

# shellcheck disable=SC2016
pstore_cmd='grep -q " /sys/fs/pstore " /proc/mounts || mount -t pstore pstore /sys/fs/pstore
for f in /sys/fs/pstore/*; do [ -e "$f" ] || continue; echo "== $f"; cat "$f"; done'

# line_ts MSG -- writes "<host-ts> MSG" to stdout, reading $EPOCHREALTIME with
# no subshell or date(1) fork.
line_ts() {
    local epoch=$EPOCHREALTIME
    printf '%(%Y-%m-%dT%H:%M:%S)T.%s%(%z)T %s\n' "${epoch%.*}" "${epoch#*.}" "${epoch%.*}" "$1"
}

# stamp TAG -- writes each stdin line to stdout as "<host-ts> [TAG] <line>".
stamp() {
    local tag=$1 line
    while IFS= read -r line || [[ -n $line ]]; do
        line_ts "[$tag] $line"
    done
    line_ts "[$tag] session ended" >&2
}

# stream TAG CMD -- runs CMD on the board in the background, stamped as TAG.
stream() {
    "${ssh[@]}" -o ServerAliveInterval=2 -o ServerAliveCountMax=3 "$host" "$2" > >(stamp "$1") 2>&1 &
    capture_pids+=("$!")
}

start_capture() {
    line_ts "capture started" >&2
    trap stop_capture EXIT
    stream kernel 'dmesg -w --time-format iso'
    stream journal 'journalctl -f -o short-iso-precise'
    stream stats "$stats_cmd"
}

disarm() {
    local cmd='echo 0 > /sys/kernel/debug/pstore/record_ftrace; : > /sys/kernel/tracing/set_ftrace_filter'
    [ -z "$prev_thresh" ] || cmd+="; sysctl -w kernel.watchdog_thresh=$prev_thresh"
    "${ssh[@]}" "$host" "$cmd" 2>&1 | stamp disarm || true
}

# Stops the capture on any exit from the install call. Idempotent and
# failure-tolerant throughout: safe as the EXIT trap and as the explicit call.
stop_capture() {
    local status=$? pid
    disarm
    line_ts "capture stopped" >&2
    if [ "${#capture_pids[@]}" -gt 0 ]; then
        for pid in "${capture_pids[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
        wait "${capture_pids[@]}" 2>/dev/null || true
    fi
    capture_pids=()
    return "$status"
}

# reset_readback BOOT_ID -- waits up to 300 s for the board to answer, as
# `just kiosk-reboot` does. A boot_id other than BOOT_ID means it reset, and
# its pstore is printed into the capture.
reset_readback() {
    local before=$1 t0=$SECONDS now
    while :; do
        now=$("${ssh[@]}" "$host" 'cat /proc/sys/kernel/random/boot_id') || now=
        [ -n "$now" ] && break
        if (( SECONDS - t0 > 300 )); then
            echo "== board did not answer within 300s -- pstore not read" >&2
            return 0
        fi
        sleep 5
    done
    if [ "$now" = "$before" ]; then
        echo "== session lost with no reset (boot_id unchanged) -- the install may still be running on the board" >&2
        return 0
    fi
    echo "== board reset during install (boot_id $before -> $now); its pstore follows" >&2
    "${ssh[@]}" "$host" "$pstore_cmd" 2>&1 | stamp pstore || true
}

main() {
    if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
        usage
        exit 0
    fi
    if [ "${1:-}" = "--check-only" ]; then
        target_activated "${2:-}" "${3:-}"
        exit $?
    fi
    [ -n "${1:-}" ] || { usage >&2; exit 2; }
    host=$1
    local root gate
    root=$(cd "$(dirname "$0")/.." && pwd)
    gate="$root/tools/reproducibility-gate.sh"
    cd "$root"

    # Directly invocable, so it cannot rely on kiosk-preflight having run.
    # --tree: what installs is already on the device.
    "$gate" --tree || exit 1
    echo "== before"
    local before
    before=$("${ssh[@]}" "$host" 'fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT; rauc status 2>&1 | grep -E "Booted|Activated|boot status"')
    echo "$before"
    local dev_epoch host_epoch skew
    dev_epoch=$("${ssh[@]}" "$host" 'date +%s')
    host_epoch=$(date +%s)
    skew=$(( host_epoch - dev_epoch ))
    echo "== clock: device epoch $dev_epoch, host $host_epoch, skew ${skew}s"
    if [ "$skew" -gt 3600 ] || [ "$skew" -lt -3600 ]; then
        echo "   WARNING: device clock off by ${skew}s -- if rauc rejects the cert below,"
        echo "            this is why: clock persistence may have failed (see #31)."
    fi
    echo "== verifying bundle signature against the device keyring"
    "${ssh[@]}" "$host" 'rauc info /data/update.raucb' \
        || { echo "bundle did not verify -- refusing to install"; exit 1; }
    local boot_id
    boot_id=$("${ssh[@]}" "$host" 'cat /proc/sys/kernel/random/boot_id')
    prev_thresh=$("${ssh[@]}" "$host" 'cat /proc/sys/kernel/watchdog_thresh') || prev_thresh=
    echo "== installing"
    start_capture
    "${ssh[@]}" "$host" "$arm_cmd" < "$root/tools/kiosk-install-ftrace-filter.txt" 2>&1 | stamp arm || true
    local rc=0
    "${ssh[@]}" -o ServerAliveInterval=5 -o ServerAliveCountMax=6 "$host" 'rauc install /data/update.raucb' || rc=$?
    stop_capture
    trap - EXIT
    if [ "$rc" -ne 0 ]; then
        reset_readback "$boot_id"
        exit "$rc"
    fi
    echo "== after"
    local after
    after=$("${ssh[@]}" "$host" 'fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT; rauc status 2>&1 | grep -E "Booted|Activated|boot status"')
    echo "$after"
    target_activated "$before" "$after" \
        || { echo "REFUSING: install did not activate the target slot"; exit 1; }
    echo "Now: just kiosk-reboot   (fallback slot stays bootable if it fails)"
}

main "$@"
