#!/usr/bin/env bash
# One non-interactive ssh to a board, with the repository's one host-key policy and keepalive.
#
#   tools/kiosk-ssh.sh root@<host> 'uptime -p'
#   tools/kiosk-ssh.sh root@<host> 'bash -s' <<'EOF'   # a script, still one round trip
#   systemctl is-active kiosk
#   cut -d' ' -f1 /proc/loadavg
#   EOF
#
# Every call is its own connection, and each costs the board CPU: batch a session's reads into one
# `bash -s` script. Host keys are neither checked nor remembered, because a slot generates its key on
# its first boot (meta-wisekiosk/recipes-connectivity/openssh/README.md). The keepalive ends a session
# 30 s after the board stops answering, longer than the ~15 s hardware watchdog.
#
# Keeps ssh stderr unfiltered (no LogLevel=ERROR) so connection errors show.
#
# A backgrounded SSH command often exits 1 even when the work succeeded; query state afterwards.
set -uo pipefail

HOST=${1:?usage: kiosk-ssh.sh <ssh-target> <command>}
shift

[ "$#" -gt 0 ] || { echo "usage: kiosk-ssh.sh <ssh-target> <command>" >&2; exit 2; }

exec ssh -oBatchMode=yes -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -oConnectTimeout=10 \
    -oServerAliveInterval=5 -oServerAliveCountMax=6 "$HOST" "$@"
