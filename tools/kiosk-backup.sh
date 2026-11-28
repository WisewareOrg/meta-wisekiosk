#!/usr/bin/env bash
# Pull a dated tarball of a board's /data to this host.
#
#   tools/kiosk-backup.sh root@<host>
#
# Pull-only, one plain stream; the tarball lands in the gitignored local/ as kiosk-data-<date>.tar.gz.
# It refuses to overwrite today's backup, and checks the archive decompresses, which catches a
# transfer cut short.
#
# Exit: 0 written and intact; 2 no host given; 1 today's backup exists, or the archive is bad.
set -euo pipefail

usage() {
    echo "usage: kiosk-backup.sh root@<host>" >&2
    exit 2
}

if [ "$#" -ne 1 ] || [ "$1" = "--help" ]; then
    usage
fi
host=$1
cd "$(dirname "$0")/.."

mkdir -p local
out="local/kiosk-data-$(date +%F).tar.gz"
if [ -e "$out" ]; then
    echo "$out exists -- move it aside rather than overwriting today's backup"
    exit 1
fi
tools/kiosk-ssh.sh "$host" 'tar -czf - -C / data' > "$out" || { echo "the transfer failed"; rm -f "$out"; exit 1; }
gzip -t "$out" || { echo "$out does not decompress -- the transfer was cut short"; rm -f "$out"; exit 1; }
echo "wrote $out ($(du -h "$out" | cut -f1))"
