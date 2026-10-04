#!/bin/bash
# run-time-to-page.sh <ssh-target> <role> <out>
#
# Three cold boots under cog. Before them, kiosk.conf is backed up and KIOSK_PROBE=1 plus
# KIOSK_PROBE_SCRIPT=/usr/share/kiosk-bootprof/time-to-page.js appended, so each boot runs the
# shipped beacon. Each boot: systemctl reboot, 120 s on this host with no probing, then one
# connection that records buildinfo and runs the shipped measure-page.sh with READ_AT 115. A boot
# it prints SUSPECT (clock stepped after kiosk start) is re-run once; a second SUSPECT is kept as
# recorded. One connection per boot, none before 120 s: kiosk-bootprof's README on why ssh is an
# instrument. kiosk.conf is restored afterwards and kiosk restarted. A kiosk.conf backup already on
# the board means an earlier run did not restore; the run refuses, exit 1.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; OUT=${3:?out}
HERE=$(dirname "$(readlink -f "$0")")
KSSH=$(git -C "$HERE" rev-parse --show-toplevel)/tools/kiosk-ssh.sh
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture" >&2; exit 2; }

{
echo "# run-time-to-page.sh role=$ROLE boots=3 wait=120 READ_AT=115"
echo "# harness $(git -C "$HERE" rev-parse HEAD)$(git -C "$HERE" diff --quiet HEAD -- . || echo " DIRTY")"
} > "$OUT"
"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<'EOF' || exit 1
C=/data/config/kiosk.conf
if [ -e $C.wpe-bak ] || [ -e $C.wpe-absent ]; then
	echo "# REFUSED: a kiosk.conf backup exists -- an earlier run did not restore"; exit 1
fi
if [ -f $C ]; then cp -p $C $C.wpe-bak || exit 1; else : > $C.wpe-absent; fi
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
printf 'KIOSK_PROBE=1\nKIOSK_PROBE_SCRIPT=/usr/share/kiosk-bootprof/time-to-page.js\n' >> $C
echo "# time-to-page.js sha256 $(sha256sum < /usr/share/kiosk-bootprof/time-to-page.js | cut -d' ' -f1)"
EOF

boot() {
	echo "=== boot $1: reboot at $(date -u +%FT%TZ) ===" >> "$OUT"
	"$KSSH" "$T" 'systemctl reboot' >> "$OUT" 2>&1
	"$KSSH" "$T" --close > /dev/null 2>&1
	sleep 120
	"$KSSH" "$T" 'sh -s' 2>&1 <<'REMOTE' | tee -a "$OUT"
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
measure-page.sh 115
REMOTE
	"$KSSH" "$T" --close > /dev/null 2>&1
}

for i in 1 2 3; do
	case "$(boot "$i")" in
	*SUSPECT*) boot "$i-rerun" > /dev/null ;;
	esac
done

"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<'EOF'
C=/data/config/kiosk.conf
if [ -f $C.wpe-bak ]; then mv $C.wpe-bak $C; elif [ -e $C.wpe-absent ]; then rm -f $C $C.wpe-absent; else echo "# NO BACKUP -- kiosk.conf left as found"; fi
systemctl restart kiosk
n=$(grep -c '^KIOSK_PROBE' $C 2>/dev/null)
echo "# restored: kiosk.conf KIOSK_PROBE lines ${n:-none, file absent}, kiosk restarted"
EOF
echo "# complete $(date -u +%FT%TZ)" >> "$OUT"
