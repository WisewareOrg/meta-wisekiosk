#!/bin/bash
# xval-capture.sh <ssh-target> <role> <outdir>
#
# Captures for cross-validating kiosk-drmgrab against `import -window root` on the X image: pair A
# (helper then import, back to back), 61 s so the clock's minute rolls, then pair B. Writes
# A.ppm A.png B.ppm B.png and capture.txt (R1 header, each capture's rc and times) to <outdir>.
# Judging is xval-judge.sh, run on these files once the crops are chosen from them.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; D=${3:?outdir}
HERE=$(dirname "$(readlink -f "$0")")
KSSH=$(git -C "$HERE" rev-parse --show-toplevel)/tools/kiosk-ssh.sh
[ -e "$D" ] && { echo "$D exists -- refusing to overwrite captures" >&2; exit 2; }
mkdir -p "$D" || exit 2

echo "# xval-capture.sh role=$ROLE started $(date -u +%FT%TZ)" > "$D/capture.txt"
for p in A B; do
	[ "$p" = B ] && sleep 61
	"$KSSH" "$T" 'sh -s' >> "$D/capture.txt" 2>&1 <<EOF
[ $p = A ] && echo "# buildinfo \$(grep '^meta-wisekiosk ' /etc/buildinfo)"
[ $p = A ] && echo "# kiosk-drmgrab sha256 \$(sha256sum < /usr/bin/kiosk-drmgrab | cut -d' ' -f1)"
echo "$p drmgrab start \$(date +%T)"
kiosk-drmgrab /tmp/xval-$p.ppm
echo "$p drmgrab rc=\$? end \$(date +%T)"
DISPLAY=:0 import -window root /tmp/xval-$p.png
echo "$p import rc=\$? end \$(date +%T)"
EOF
	for ext in ppm png; do
		"$KSSH" "$T" "cat /tmp/xval-$p.$ext && rm -f /tmp/xval-$p.$ext" > "$D/$p.$ext" ||
			echo "$p.$ext fetch failed" >> "$D/capture.txt"
	done
done
echo "# complete $(date -u +%FT%TZ)" >> "$D/capture.txt"
