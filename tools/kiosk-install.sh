#!/usr/bin/env bash
# Install a RAUC bundle on a board and show slot state. Does NOT reboot --
# inspect `rauc status` first, then `just kiosk-reboot`.
#
#   tools/kiosk-install.sh root@<host> <bundle>
#   tools/kiosk-install.sh --check-only <before> <after>
#
# One install per board at a time from this host, by the address its host name resolves to (a second is
# refused, naming the holder's pid and checkout). A script killed alone frees the lock at once while rauc goes
# on installing; a later call is then refused by rauc only, after its arming.
#
# Every install goes through this script: just kiosk-ota, tools/rauc-rotate.sh
# and the target suite's update tests. The board streams BUNDLE: for the length
# of the install, a pinned nginx container on a port docker chooses serves it,
# holding only BUNDLE, in memory, and the board runs `rauc install` on its URL
# at the address its own ssh session comes from (SSH_CLIENT). rauc checks the
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
# During `rauc install` it streams the board's kernel log, journal and
# once-a-second memory/load/SD/undervoltage stats to the console, timestamped
# on this host, and arms two kernel recorders that survive a reset: the
# soft-lockup detector at kernel.watchdog_thresh=1 and the pstore ftrace zone
# over the functions in kiosk-install-ftrace-filter.txt. Arming deletes any
# dmesg and ftrace records already in pstore; disarming restores the threshold
# and empties the filter. The install's session ends once the board stops
# answering its keepalives. If it ends that way and the board answers again
# with a new boot_id, the board's pstore is printed into the same capture.
#
# --check-only BEFORE AFTER runs target_activated directly against two
# fw_printenv/rauc-status blocks, with no ssh and no device.
#
# Exit: 0 installed and the target slot activated, or --check-only passed;
# 1 no bundle at the path, the gate failed, another install holds the board,
# the bundle server did not start, rauc refused or failed the install, the
# target slot did not activate, or --check-only failed; 2 no host or no bundle given. An ssh or rauc command
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
server=

ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
host=
url=
served=0
capturing=0
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

# board_address HOST -- the address HOST names (user@ stripped, ssh's HostName, then its first IPv4), or the
# stripped name when nothing resolves, so two names for one board meet on one install lock.
board_address() {
    local name=${1#*@} resolved addr
    resolved=$(ssh -G "$name" 2>/dev/null | awk '$1 == "hostname" { print $2 }' | head -n 1) || resolved=
    resolved=${resolved:-$name}
    addr=$(getent ahostsv4 "$resolved" 2>/dev/null | awk 'NR == 1 { print $1 }') || addr=
    echo "${addr:-$resolved}"
}

# stream TAG CMD -- runs CMD on the board in the background, stamped as TAG.
stream() {
    # In a subshell that closes the install lock's descriptor first, so neither the ssh nor its stamp process holds
    # the lock; the subshell becomes the ssh, so $! is the ssh.
    (
        exec 8>&-
        exec "${ssh[@]}" -o ServerAliveInterval=2 -o ServerAliveCountMax=3 "$host" "$2" > >(stamp "$1") 2>&1
    ) &
    capture_pids+=("$!")
}

# arm ROOT -- arms the recorders, reading the filter beside this script.
arm() {
    "${ssh[@]}" "$host" "$arm_cmd" < "$1/tools/kiosk-install-ftrace-filter.txt" 2>&1 | stamp arm || true
}

start_capture() {
    line_ts "capture started" >&2
    capturing=1
    stream kernel 'dmesg -w --time-format iso'
    stream journal 'journalctl -f -o short-iso-precise'
    stream stats "$stats_cmd"
}

disarm() {
    local cmd='echo 0 > /sys/kernel/debug/pstore/record_ftrace; : > /sys/kernel/tracing/set_ftrace_filter'
    [ -z "$prev_thresh" ] || cmd+="; sysctl -w kernel.watchdog_thresh=$prev_thresh"
    "${ssh[@]}" "$host" "$cmd" 2>&1 | stamp disarm || true
}

# Stops the capture. Idempotent and failure-tolerant throughout: safe from
# cleanup and as the explicit call.
stop_capture() {
    local pid
    [ "$capturing" -eq 1 ] || return 0
    capturing=0
    disarm
    line_ts "capture stopped" >&2
    if [ "${#capture_pids[@]}" -gt 0 ]; then
        for pid in "${capture_pids[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
        wait "${capture_pids[@]}" 2>/dev/null || true
    fi
    capture_pids=()
}

# serve BUNDLE -- serves BUNDLE on a port docker chooses and sets url to it at the
# address the board's ssh session comes from.
serve() {
    local bundle=$1 addr t0 existing owner name port
    # shellcheck disable=SC2016 # the board's shell expands SSH_CLIENT
    addr=$("${ssh[@]}" "$host" 'echo "${SSH_CLIENT%% *}"')
    [ -n "$addr" ] || { echo "the board did not report its ssh client address"; return 1; }
    # one listing, so a failed read removes nothing; a server whose labelled pid is dead is removed
    while read -r existing owner; do
        ps -p "$owner" >/dev/null 2>&1 || docker rm -f "$existing" >/dev/null 2>&1 || true
    done < <(docker ps -a --filter "label=kiosk-install.pid" --format '{{.ID}} {{.Label "kiosk-install.pid"}}')
    docker image inspect "$nginx_image" >/dev/null 2>&1 || docker pull -q "$nginx_image" >/dev/null \
        || { echo "could not pull $nginx_image"; return 1; }
    server=$(docker run -d --rm --label "kiosk-install.pid=$$" -p 80 \
        --tmpfs /usr/share/nginx/html "$nginx_image") \
        || { echo "could not start the bundle server"; return 1; }
    served=1
    port=$(docker port "$server" 80/tcp)
    port=${port%%$'\n'*}
    port=${port##*:}
    [ -n "$port" ] || { echo "docker did not report the bundle server's port"; return 1; }
    name=$(basename "$bundle")
    docker exec -i "$server" sh -c 'cat > "/usr/share/nginx/html/$1"' sh "$name" < "$bundle" \
        || { echo "could not copy the bundle into the server"; return 1; }
    t0=$SECONDS
    until curl -sf -o /dev/null -r 0-0 "http://127.0.0.1:$port/$name"; do
        (( SECONDS - t0 < 30 )) || { echo "the bundle server did not answer within 30s"; return 1; }
        sleep 1
    done
    url="http://$addr:$port/$name"
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
# `just kiosk-reboot` does, then disarms it. A boot_id other than BOOT_ID
# means it reset, and its pstore is printed into the capture.
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
    disarm
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

    # One install per board from this host (docs/testing.md §"Running it"). The lock is the board's address, at
    # a fixed path; the holder writes its pid and checkout into it.
    local lock holder
    lock="/tmp/kiosk-install-$(board_address "$host" | tr -c 'A-Za-z0-9._:\n-' _).lock"
    exec 8>>"$lock"
    if ! flock -n 8; then
        read -r holder < "$lock" || holder="unknown holder"
        echo "another install holds $host (pid and checkout: $holder)"
        exit 1
    fi
    printf '%s %s\n' "$$" "$PWD" > "$lock"

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
    prev_thresh=$("${ssh[@]}" "$host" 'cat /proc/sys/kernel/watchdog_thresh') || prev_thresh=
    echo "== installing"
    start_capture
    arm "$root"
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
