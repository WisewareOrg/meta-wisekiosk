#!/bin/bash
# run-time-to-page.sh <ssh-target> <role> <out>
#
# Three cold boots under X. Before them, the shipped time-to-page.js beacon goes in as surf's
# script.js and time-to-page-x.sh onto /data. Each boot: systemctl reboot, 120 s on this host with
# no probing, then one connection that records buildinfo and runs time-to-page-x.sh with READ_AT
# 115. A boot it prints SUSPECT (clock stepped after kiosk start) is re-run once; a second SUSPECT
# is kept as recorded. One connection per boot, none before 120 s: kiosk-bootprof's README on why
# ssh is an instrument. script.js is emptied afterwards; the next boot runs without the beacon.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; OUT=${3:?out}
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
KSSH=$ROOT/tools/kiosk-ssh.sh
JS=$ROOT/meta-wisekiosk/recipes-core/kiosk-bootprof/files/time-to-page.js
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture" >&2; exit 2; }

{
echo "# run-time-to-page.sh role=$ROLE boots=3 wait=120 READ_AT=115"
echo "# time-to-page.js sha256 $(sha256sum < "$JS" | cut -d' ' -f1)"
} > "$OUT"
"$KSSH" "$T" 'cat > /home/root/.surf/script.js' < "$JS" || exit 1
"$KSSH" "$T" 'cat > /data/time-to-page-x.sh' < "$HERE/time-to-page-x.sh" || exit 1

boot() {
	echo "=== boot $1: reboot at $(date -u +%FT%TZ) ===" >> "$OUT"
	"$KSSH" "$T" 'systemctl reboot' >> "$OUT" 2>&1
	"$KSSH" "$T" --close > /dev/null 2>&1
	sleep 120
	"$KSSH" "$T" 'sh -s' 2>&1 <<'REMOTE' | tee -a "$OUT"
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
sh /data/time-to-page-x.sh 115
REMOTE
	"$KSSH" "$T" --close > /dev/null 2>&1
}

for i in 1 2 3; do
	case "$(boot "$i")" in
	*SUSPECT*) boot "$i-rerun" > /dev/null ;;
	esac
done

"$KSSH" "$T" ': > /home/root/.surf/script.js; rm -f /data/time-to-page-x.sh' >> "$OUT" 2>&1
echo "# complete $(date -u +%FT%TZ)" >> "$OUT"
