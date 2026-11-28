#!/usr/bin/env bash
# Self-test for tools/kiosk-ssh.sh: the ssh it runs.
#
#   tests/prechecks/kiosk-ssh-test.sh
#
# Runs the SHIPPED script with a stub `ssh` first on PATH that records its argv, and compares that
# argv with the options the helper promises: non-interactive, no host-key check or record, a 10 s
# connect timeout, a keepalive of 5 s by 6, the host, then the command. A call with no command
# exits 2 without running ssh.
set -uo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
mkdir "$scratch/bin"
cat > "$scratch/bin/ssh" <<'STUB'
#!/bin/bash
printf '%s\n' "$@" > "$ARGV"
STUB
chmod +x "$scratch/bin/ssh"
export PATH=$scratch/bin:$PATH ARGV=$scratch/argv

expected='-oBatchMode=yes
-oStrictHostKeyChecking=no
-oUserKnownHostsFile=/dev/null
-oConnectTimeout=10
-oServerAliveInterval=5
-oServerAliveCountMax=6
root@board
uptime -p'

fails=0
"$root/tools/kiosk-ssh.sh" root@board 'uptime -p'
if [ "$(cat "$ARGV")" = "$expected" ]; then
    echo "ok    the ssh argv is the promised one"
else
    echo "FAIL  the ssh argv differs:"
    sed 's/^/      /' "$ARGV"
    fails=$((fails + 1))
fi

rm -f "$ARGV"
"$root/tools/kiosk-ssh.sh" root@board 2>/dev/null
rc=$?
if [ "$rc" -eq 2 ] && [ ! -e "$ARGV" ]; then
    echo "ok    no command exits 2 without running ssh"
else
    echo "FAIL  no command: exit $rc, ssh ran: $([ -e "$ARGV" ] && echo yes || echo no)"
    fails=$((fails + 1))
fi

echo "kiosk-ssh: $fails case(s) failed"
[ "$fails" -eq 0 ]
