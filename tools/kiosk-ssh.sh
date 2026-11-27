#!/usr/bin/env bash
# One SSH connection, reused, for a debugging session made of small commands.
#
#   tools/kiosk-ssh.sh root@<host> 'uptime -p'
#   tools/kiosk-ssh.sh root@<host> 'bash -s' <<'EOF'   # a script, still one round trip
#   systemctl is-active kiosk
#   cut -d' ' -f1 /proc/loadavg
#   EOF
#   tools/kiosk-ssh.sh root@<host> --close             # drop the master early
#
# Multiplexes over one ssh control master that lives on this host and persists 30 minutes; nothing
# is installed on the device. A device reboot orphans the master: ServerAliveInterval/CountMax
# bound it at about 60s, and --close drops it.
#
# The control path is "$HOME/.ssh/kiosk-%C" and caps at about 108 characters; a longer one fails
# every call with `too long for Unix domain socket`. %C is a fixed-length hash.
#
# Keeps ssh stderr unfiltered (no LogLevel=ERROR) so connection errors show.
#
# A backgrounded SSH command often exits 1 even when the work succeeded; query state afterwards.
set -uo pipefail

HOST=${1:?usage: kiosk-ssh.sh <ssh-target> <command> | <ssh-target> --close}
shift

CONTROL="$HOME/.ssh/kiosk-%C"

ssh_opts=(
    -o BatchMode=yes
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile=/dev/null
    -o ConnectTimeout=10
    -o ControlMaster=auto
    -o ControlPath="$CONTROL"
    -o ControlPersist=30m
    -o ServerAliveInterval=15
    -o ServerAliveCountMax=4
)

if [ "${1:-}" = "--close" ]; then
    # No master running is not an error.
    ssh "${ssh_opts[@]}" -O exit "$HOST" 2>&1 | grep -v 'No such file or directory' || true
    exit 0
fi

[ "$#" -gt 0 ] || { echo "usage: kiosk-ssh.sh <ssh-target> <command>" >&2; exit 2; }

exec ssh "${ssh_opts[@]}" "$HOST" "$@"
