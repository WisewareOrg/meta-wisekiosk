#!/usr/bin/env bash
# Reboot a board and wait for the kiosk to answer again.
#
#   tools/kiosk-reboot.sh root@<host> [timeout]
#
# Reads the board's boot_id, reboots it, and polls every 5 s until the boot_id differs. The clock
# starts before the reboot call, so a hang in it counts against the timeout (default 300 s).
#
# Exit: 0 the board is back with a new boot_id; 2 no host given; 1 it did not come back in time.
set -euo pipefail

usage() {
    echo "usage: kiosk-reboot.sh root@<host> [timeout]" >&2
    exit 2
}

if [ -z "${1:-}" ]; then
    usage
fi
host=$1
timeout=${2:-300}

ssh=("$(cd "$(dirname "$0")" && pwd)/kiosk-ssh.sh")
boot_id='cat /proc/sys/kernel/random/boot_id'

before=$("${ssh[@]}" "$host" "$boot_id" 2>/dev/null) || before=
t0=$(date +%s)
"${ssh[@]}" "$host" 'systemctl reboot' >/dev/null 2>&1 || true
while :; do
    now=$("${ssh[@]}" "$host" "$boot_id" 2>/dev/null) || now=
    [ -n "$now" ] && [ "$now" != "$before" ] && break
    [ $(($(date +%s) - t0)) -gt "$timeout" ] && { echo "did not come back in ${timeout}s"; exit 1; }
    sleep 5
done
echo "back after $(($(date +%s) - t0))s, boot_id $now"
