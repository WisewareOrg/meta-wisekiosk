#!/bin/bash
# check-cog-cache-path.sh <ssh-target> -- read-only. Where cog actually puts its cache, since
# /home/root/.cache/cog (what the smoothness/soak drivers rm -rf) doesn't exist.
set -u
T=${1:?ssh-target}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
"$KSSH" "$T" 'sh -s' <<'EOF'
echo "=== getent passwd root ==="
getent passwd root
echo "=== systemctl show kiosk -p Environment ==="
systemctl show kiosk -p Environment
echo "=== cog's actual environ (HOME/XDG_*) ==="
tr '\0' '\n' < /proc/$(pidof cog)/environ | grep -E '^(HOME|XDG_)'
echo "=== ls -la /root/.cache /home/root/.cache ==="
ls -la /root/.cache /home/root/.cache 2>&1
echo "=== find / -xdev -type d -name cog ==="
find / -xdev -type d -name cog 2>/dev/null
echo "=== du -sh of each found dir ==="
for d in $(find / -xdev -type d -name cog 2>/dev/null); do
  du -sh "$d" 2>&1
done
EOF
