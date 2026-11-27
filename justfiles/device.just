# Device recipes over SSH; each assumes root@<host> access.

# Show RAUC status on a running device
[group('device')]
rauc-status host:
    ssh root@{{host}} "rauc status"

# Reboot a device
[group('device')]
reboot host:
    ssh root@{{host}} "reboot"

# Show system status on a running device
[group('device')]
[script('bash')]
status host:
    # One non-interactive probe (BatchMode) before the tolerant per-command reads.
    ssh -o BatchMode=yes -o ConnectTimeout=10 root@{{host}} true || { echo "cannot reach root@{{host}}: unreachable, or host key not in known_hosts" >&2; exit 1; }
    echo "=== RAUC Status ==="
    ssh root@{{host}} "rauc status" || true
    echo ""
    echo "=== Disk Usage ==="
    ssh root@{{host}} "df -h" || true
    echo ""
    echo "=== Uptime ==="
    ssh root@{{host}} "uptime" || true

# === Diagnostics ===
#
# Thin wrappers over tools/kiosk-*, except bootprofile, which runs through the bench runner.

[group('device')]
[script('bash')]
[doc("Sweep a /24 and report Raspberry Pi OUIs from the best neighbour table available")]
find cidr:
    tools/kiosk-find.sh {{cidr}}
    rc=$?
    if [ $rc -eq 3 ]; then
        echo "exit 3: no L2 view of {{cidr}}. Anything printed above is reachability only," >&2
        echo "        not an identification, and no line of it says the subnet is empty." >&2
    fi
    exit $rc

# Run from the host serving the page; kiosk-addr is the kiosk's address.
[group('device')]
[doc("Infer browser state from TCP connections to the served page")]
tcp-state kiosk-addr port="8080":
    tools/kiosk-tcp-state.sh {{kiosk-addr}} {{port}}

[group('device')]
[doc("Read the panel's buffer into a PNG, and fail if it is blank")]
screenshot host out="":
    tools/kiosk-screenshot.py root@{{host}} {{out}}

# n is a sample count, one sample per 5 minutes.
[group('device')]
[doc("Read the soak log summary from the device")]
soak-summary host n="24":
    tools/kiosk-ssh.sh root@{{host}} 'kiosk-soak.sh --summary {{n}}'

# Reboots the device; samples land in the gitignored local/.
[group('device')]
[doc("Profile one boot end to end on the board LG_ENV names; leaves the checkout on a detached HEAD")]
bootprofile:
    bench test HEAD --skip-build -- tests/diagnostics -k boot_profile -rP

# Pull-only, one plain stream; the tarball lands in the gitignored local/. host is an ssh target.
[group('device')]
[script('bash')]
[doc("Pull a dated tarball of the device's /data to this host")]
kiosk-backup host=kiosk-host:
    SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
    mkdir -p local
    OUT="local/kiosk-data-$(date +%F).tar.gz"
    if [ -e "$OUT" ]; then
        echo "$OUT exists -- move it aside rather than overwriting today's backup"
        exit 1
    fi
    $SSH {{host}} 'tar -czf - -C / data' > "$OUT"
    # gzip -t detects a truncated stream.
    gzip -t "$OUT" || { echo "$OUT does not decompress -- the transfer was cut short"; rm -f "$OUT"; exit 1; }
    echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
