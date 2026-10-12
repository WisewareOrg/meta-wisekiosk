#!/bin/bash
# check-coredump.sh <ssh-target> -- read-only. Where cog's crash-on-stop core dumps land, how
# big, how fast they grow, and which filesystem holds them.
set -u
T=${1:?ssh-target}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
"$KSSH" "$T" 'sh -s' <<'EOF'
echo "=== coredumpctl list ==="
coredumpctl list 2>&1 | tail -20
echo "=== /var/lib/systemd/coredump ==="
ls -la /var/lib/systemd/coredump/ 2>&1
du -sh /var/lib/systemd/coredump/ 2>&1
echo "=== which filesystem ==="
df -h /var/lib/systemd/coredump 2>&1
mount | grep -E " / | /data "
echo "=== systemd-coredump config ==="
cat /etc/systemd/coredump.conf 2>&1
cat /etc/systemd/coredump.conf.d/*.conf 2>&1
EOF
