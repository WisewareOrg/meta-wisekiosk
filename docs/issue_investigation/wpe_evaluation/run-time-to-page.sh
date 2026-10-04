#!/bin/bash
# run-time-to-page.sh <ssh-target> <role> <out>
#
# Three cold boots under X. Each: systemctl reboot, 120 s on this host with no probing, then one
# connection that records buildinfo and runs the shipped measure-surf.sh with READ_AT 115. One
# connection per boot, none before 120 s: kiosk-bootprof's README on why ssh is an instrument.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; OUT=${3:?out}
HERE=$(dirname "$(readlink -f "$0")")
KSSH=$(git -C "$HERE" rev-parse --show-toplevel)/tools/kiosk-ssh.sh
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture" >&2; exit 2; }

echo "# run-time-to-page.sh role=$ROLE boots=3 wait=120 READ_AT=115" > "$OUT"
for i in 1 2 3; do
	echo "=== boot $i: reboot at $(date -u +%FT%TZ) ===" >> "$OUT"
	"$KSSH" "$T" 'systemctl reboot' >> "$OUT" 2>&1
	"$KSSH" "$T" --close > /dev/null 2>&1
	sleep 120
	"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<'REMOTE'
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
measure-surf.sh 115
REMOTE
	"$KSSH" "$T" --close > /dev/null 2>&1
done
echo "# complete $(date -u +%FT%TZ)" >> "$OUT"
