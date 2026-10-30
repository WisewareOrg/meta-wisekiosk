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
# During `rauc install` it streams the board's kernel log and journal to the
# console, timestamped on this host.
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

capture_pids=()

# stamp TAG -- writes each stdin line to stdout as "<host-ts> [TAG] <line>",
# reading $EPOCHREALTIME once per line with no subshell or date(1) fork.
stamp() {
    local tag=$1 line epoch
    while IFS= read -r line || [[ -n $line ]]; do
        epoch=$EPOCHREALTIME
        printf '%(%Y-%m-%dT%H:%M:%S)T.%s%(%z)T [%s] %s\n' "${epoch%.*}" "${epoch#*.}" "${epoch%.*}" "$tag" "$line"
    done
    epoch=$EPOCHREALTIME
    printf '%(%Y-%m-%dT%H:%M:%S)T.%s%(%z)T [%s] session ended\n' "${epoch%.*}" "${epoch#*.}" "${epoch%.*}" "$tag" >&2
}

# Stops the capture on any exit from the install call. Idempotent and
# failure-tolerant throughout: safe as the EXIT trap and as the explicit call.
stop_capture() {
    local status=$? epoch=$EPOCHREALTIME pid
    printf '%(%Y-%m-%dT%H:%M:%S)T.%s%(%z)T capture stopped\n' "${epoch%.*}" "${epoch#*.}" "${epoch%.*}" >&2
    if [ "${#capture_pids[@]}" -gt 0 ]; then
        for pid in "${capture_pids[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
        wait "${capture_pids[@]}" 2>/dev/null || true
    fi
    capture_pids=()
    return "$status"
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
    local host=$1
    local root gate
    root=$(cd "$(dirname "$0")/.." && pwd)
    gate="$root/tools/reproducibility-gate.sh"
    cd "$root"
    local ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)

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
    echo "== installing"
    local epoch=$EPOCHREALTIME
    printf '%(%Y-%m-%dT%H:%M:%S)T.%s%(%z)T capture started\n' "${epoch%.*}" "${epoch#*.}" "${epoch%.*}" >&2
    trap stop_capture EXIT
    "${ssh[@]}" -o ServerAliveInterval=2 -o ServerAliveCountMax=3 "$host" 'dmesg -w --time-format iso' > >(stamp kernel) 2>&1 &
    capture_pids+=("$!")
    "${ssh[@]}" -o ServerAliveInterval=2 -o ServerAliveCountMax=3 "$host" 'journalctl -f -o short-iso-precise' > >(stamp journal) 2>&1 &
    capture_pids+=("$!")
    "${ssh[@]}" "$host" 'rauc install /data/update.raucb'
    stop_capture
    trap - EXIT
    echo "== after"
    local after
    after=$("${ssh[@]}" "$host" 'fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT; rauc status 2>&1 | grep -E "Booted|Activated|boot status"')
    echo "$after"
    target_activated "$before" "$after" \
        || { echo "REFUSING: install did not activate the target slot"; exit 1; }
    echo "Now: just kiosk-reboot   (fallback slot stays bootable if it fails)"
}

main "$@"
