#!/usr/bin/env bash
# Install a RAUC bundle on a board and show slot state. Does NOT reboot --
# inspect `rauc status` first, then `just kiosk-reboot`.
#
#   tools/kiosk-install.sh root@<host> <bundle>
#   tools/kiosk-install.sh --check-only <before> <after>
#
# Every install goes through this script: just kiosk-ota, tools/rauc-rotate.sh
# and the target suite's update tests. The board streams BUNDLE: for the length
# of the install, a pinned nginx container on this host's port 80 serves it,
# with only BUNDLE mounted, and the board runs `rauc install` on its URL at the
# address its own ssh session comes from (SSH_CLIENT). rauc checks the
# signature against the board's keyring before it writes anything.
#
# Checks, in order: the reproducibility gate against the tree containing this
# script, regardless of the caller's working directory (--tree: what installs
# is already on the device); the device clock's skew from the host (reported,
# never set -- a cold clock after a fresh slot's first boot is the documented
# cause of a "certificate is not yet valid" refusal below, see #31); and, after
# `rauc install`, that BOOT_ORDER now leads with the slot that was NOT booted
# before, with that slot's *_LEFT counter reset above 0 (target_activated).
#
# Before `rauc install` it deletes any dmesg and ftrace records already in
# pstore, so a read-back after a reset holds only that install's. During it, it
# streams the board's kernel log, journal and once-a-second
# memory/load/SD/undervoltage stats to the console, timestamped on this host.
# The install's session ends once the board stops answering its keepalives. If
# it ends that way and the board answers again with a new boot_id, the board's
# pstore is printed into the same capture.
#
# --check-only BEFORE AFTER runs target_activated directly against two
# fw_printenv/rauc-status blocks, with no ssh and no device.
#
# Exit: 0 installed and the target slot activated, or --check-only passed;
# 1 no bundle at the path, the gate failed, the bundle server did not start,
# rauc refused or failed the install, the target slot did not activate, or
# --check-only failed; 2 no host or no bundle given. An ssh or rauc command
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

nginx_image="nginx:1.30.8-alpine@sha256:6437a63b5c529f0e06162b3f593c0154cff6fa2ea0f94fd7c27928cb399e022d"
server=kiosk-bundle-server

ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
host=
url=
served=0
capturing=0
capture_pids=()

# Single-quoted throughout: every $ below is the remote busybox shell's.
# shellcheck disable=SC2016
stats_cmd='h=; for d in /sys/class/hwmon/hwmon*; do [ "$(cat "$d"/name 2>/dev/null)" = rpi_volt ] && h="$d"; done; while true; do m=; for f in MemFree Dirty Writeback; do set -- $(grep "^$f:" /proc/meminfo); m="$m$1$2 "; done; set -- $(cat /proc/loadavg); l="load=$1 $2 $3"; set -- $(cat /sys/block/mmcblk0/stat); k="mmc=$*"; u=$(cat "$h/in0_lcrit_alarm"); echo "$m$l $k uv=$u"; sleep 1; done'

pstore_mount='grep -q " /sys/fs/pstore " /proc/mounts || mount -t pstore pstore /sys/fs/pstore || echo "pstore did not mount"'

# Each step reports its own failure: failing to clear never stops the install.
clear_cmd="$pstore_mount
rm -f /sys/fs/pstore/dmesg-ramoops-* /sys/fs/pstore/ftrace-ramoops-0"

# shellcheck disable=SC2016
pstore_cmd="$pstore_mount"'
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

# clear_pstore -- deletes the dmesg and ftrace records already in pstore.
clear_pstore() {
    "${ssh[@]}" "$host" "$clear_cmd" 2>&1 | stamp clear || true
}

start_capture() {
    line_ts "capture started" >&2
    capturing=1
    stream kernel 'dmesg -w --time-format iso'
    stream journal 'journalctl -f -o short-iso-precise'
    stream stats "$stats_cmd"
}

# Stops the capture. Idempotent and failure-tolerant throughout: safe from
# cleanup and as the explicit call.
stop_capture() {
    local pid
    [ "$capturing" -eq 1 ] || return 0
    capturing=0
    line_ts "capture stopped" >&2
    if [ "${#capture_pids[@]}" -gt 0 ]; then
        for pid in "${capture_pids[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
        wait "${capture_pids[@]}" 2>/dev/null || true
    fi
    capture_pids=()
}

# serve BUNDLE -- serves BUNDLE on this host's port 80 and sets url to it at the
# address the board's ssh session comes from.
serve() {
    local bundle=$1 addr t0 existing owner
    # shellcheck disable=SC2016 # the board's shell expands SSH_CLIENT
    addr=$("${ssh[@]}" "$host" 'echo "${SSH_CLIENT%% *}"')
    [ -n "$addr" ] || { echo "the board did not report its ssh client address"; return 1; }
    existing=$(docker ps -aq --filter "name=^${server}\$")
    if [ -n "$existing" ]; then
        owner=$(docker inspect -f '{{index .Config.Labels "kiosk-install.pid"}}' "$existing" 2>/dev/null) || owner=
        if [ -n "$owner" ] && ps -p "$owner" >/dev/null 2>&1; then
            echo "another install on this host (pid $owner) is serving a bundle"
            return 1
        fi
        # left by an install that was killed before its cleanup ran
        docker rm -f "$existing" >/dev/null 2>&1 || true
    fi
    docker image inspect "$nginx_image" >/dev/null 2>&1 || docker pull -q "$nginx_image" >/dev/null \
        || { echo "could not pull $nginx_image"; return 1; }
    docker run -d --rm --name "$server" --label "kiosk-install.pid=$$" -p 80:80 \
        -v "$bundle:/usr/share/nginx/html/$(basename "$bundle"):ro" "$nginx_image" >/dev/null \
        || { echo "could not start the bundle server on port 80"; return 1; }
    served=1
    t0=$SECONDS
    until curl -sf -o /dev/null -r 0-0 "http://127.0.0.1/$(basename "$bundle")"; do
        (( SECONDS - t0 < 30 )) || { echo "the bundle server did not answer within 30s"; return 1; }
        sleep 1
    done
    url="http://$addr/$(basename "$bundle")"
    echo "== serving $bundle at $url"
}

stop_server() {
    [ "$served" -eq 1 ] || return 0
    served=0
    docker stop "$server" >/dev/null 2>&1 || true
}

# On any exit: the server first, so a failing capture stop cannot leave it up.
cleanup() {
    stop_server
    stop_capture || true
}

# reset_readback BOOT_ID -- waits up to 300 s for the board to answer, as
# `just kiosk-reboot` does. A boot_id other than BOOT_ID means it reset, and its
# pstore is printed into the capture.
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
    if [ -z "${1:-}" ] || [ -z "${2:-}" ]; then
        usage >&2
        exit 2
    fi
    [ -f "$2" ] || { echo "no bundle at $2"; exit 1; }
    host=$1
    local root gate bundle
    bundle=$(readlink -f "$2")
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
    trap cleanup EXIT
    serve "$bundle" || exit 1
    local boot_id
    boot_id=$("${ssh[@]}" "$host" 'cat /proc/sys/kernel/random/boot_id')
    echo "== installing"
    start_capture
    clear_pstore
    local rc=0
    "${ssh[@]}" -o ServerAliveInterval=5 -o ServerAliveCountMax=6 "$host" "rauc install $url" || rc=$?
    stop_capture
    stop_server
    if [ "$rc" -ne 0 ]; then
        [ "$rc" -ne 255 ] || reset_readback "$boot_id"
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
