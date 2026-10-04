#!/bin/bash
# run-smoothness.sh <ssh-target> <role> <out>
#
# One smoothness capture under cog, the sequence of ../gpu_compositing/run-appliance.sh with the
# WPE readback:
#   pre-run  screenshot into local/ for the card state, retried every 10 s until not blank;
#            blank or failing at 120 s is VOID, exit 3, before anything is deployed
#   deploy   p7_min.js to /home/root/kiosk-probe.js; kiosk.conf backed up, KIOSK_PROBE=1 appended
#   capture  rm -rf /home/root/.cache/cog; systemctl restart kiosk; sleep 585; the kiosk journal's
#            MP| lines since the restart (cog prints each title as "TITLE <title>"), loadavg,
#            MemAvailable
#   restore  kiosk.conf from its backup, probe removed, cache cleared, kiosk restarted
# Around it: the R1 header run-appliance.sh records, the active CRTC mode read from DRM debugfs
# before deploy and after readback (anything but 1280x720 on either read is VOID, exit 3), the
# served bundle name from cog's cache, and kiosk NRestarts. A kiosk.conf backup already on the
# board means an earlier run did not restore; the run refuses, exit 1, and leaves it alone.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; OUT=${3:?out}
SLEEP=585
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
KSSH=$ROOT/tools/kiosk-ssh.sh
PROBE=$HERE/../gpu_compositing/p7_min.js
SHOT=$ROOT/local/wpe-pre-$(basename "$OUT" .txt).png
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture" >&2; exit 2; }

# kiosk.conf is restored on any exit once this run has backed it up, interrupts included.
RESTORE_PENDING=0
restore_conf() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<'RESTORE'
C=/data/config/kiosk.conf
if [ -f $C.wpe-bak ]; then mv $C.wpe-bak $C; elif [ -e $C.wpe-absent ]; then rm -f $C $C.wpe-absent; else echo "# NO BACKUP -- kiosk.conf left as found"; fi
rm -f /home/root/kiosk-probe.js
rm -rf /home/root/.cache/cog
systemctl restart kiosk
n=$(grep -c '^KIOSK_PROBE' $C 2>/dev/null)
echo "# restored: kiosk.conf KIOSK_PROBE lines ${n:-none, file absent}, kiosk restarted"
RESTORE
}
trap restore_conf EXIT
trap 'exit 1' INT TERM HUP

mode() { "$KSSH" "$T" 'grep "mode:" /sys/kernel/debug/dri/0/state' 2>&1; }
live720() { printf '%s\n' "$1" | grep -c 'mode: "1280x720"'; }

for wait in 0 10 20 30 40 50 60 70 80 90 100 110 120; do
	[ "$wait" -gt 0 ] && { rm -f "$SHOT"; sleep 10; }
	"$ROOT/tools/kiosk-screenshot.sh" "$T" "$SHOT" && break
	[ "$wait" -eq 120 ] && { echo "VOID: pre-run screenshot blank or failing for 120 s -- $SHOT" >&2; exit 3; }
done

{
echo "# run-smoothness.sh role=$ROLE probe=$(basename "$PROBE") sleep=$SLEEP"
echo "# harness $(git -C "$HERE" rev-parse HEAD)$(git -C "$HERE" diff --quiet HEAD -- . ../gpu_compositing ../../../tools || echo " DIRTY")"
echo "# started $(date -u +%FT%TZ)"
echo "# pre-run screenshot local/$(basename "$SHOT")"
echo "# probe sha256 local    $(sha256sum < "$PROBE" | cut -d' ' -f1)"
"$KSSH" "$T" 'sh -s' <<'PRE'
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
echo "# config.json sha256 $(sha256sum /data/config/config.json | cut -d' ' -f1)"
sed 's/^\(KIOSK_URL=\).*/\1<masked>/; s/^/# kiosk.conf /' /data/config/kiosk.conf
PRE
"$KSSH" "$T" 'cat /data/config/config.json' | python3 -c 'import json,sys; c=json.load(sys.stdin); m=[x for x in c["modules"] if x["module"]=="park_wait_times"]; print("# park_wait_times.rotation_interval_seconds", m[0].get("options",{}).get("rotation_interval_seconds","ABSENT (schema default)") if m else "NO park_wait_times MODULE")'
} > "$OUT"

M0=$(mode); printf '%s\n' "$M0" | sed 's/^/# mode-before /' >> "$OUT"

"$KSSH" "$T" 'cat > /home/root/kiosk-probe.js' < "$PROBE" || { echo "# DEPLOY FAILED" >> "$OUT"; exit 1; }
RESTORE_PENDING=1
"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<'DEPLOY'
C=/data/config/kiosk.conf
if [ -e $C.wpe-bak ] || [ -e $C.wpe-absent ]; then
	echo "# REFUSED: a kiosk.conf backup exists -- an earlier run did not restore"; exit 3
fi
if [ -f $C ]; then cp -p $C $C.wpe-bak || exit 1; else : > $C.wpe-absent; fi
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_PROBE=1' >> $C
echo "# probe sha256 deployed $(sha256sum < /home/root/kiosk-probe.js | cut -d' ' -f1)"
DEPLOY
rc=$?
[ $rc -eq 3 ] && RESTORE_PENDING=0
[ $rc -eq 0 ] || exit 1

{
echo "# capture start $(date -u +%FT%TZ)"
"$KSSH" "$T" 'sh -s' 2>&1 <<EOF
rm -rf /home/root/.cache/cog
systemctl restart kiosk
S=\$(date +%s)
echo "restarted, sleeping $SLEEP"
sleep $SLEEP
echo "=== journal MP| ==="
journalctl -u kiosk --since @\$S -o cat --no-pager | grep 'MP|'
echo "LOAD \$(cat /proc/loadavg)"
echo "MEM \$(grep MemAvailable /proc/meminfo)"
echo "=== DONE ==="
EOF
echo "# capture end $(date -u +%FT%TZ)"
} >> "$OUT"

M1=$(mode); printf '%s\n' "$M1" | sed 's/^/# mode-after /' >> "$OUT"
"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<'POST'
echo "# bundle $(grep -rhoE 'index-[A-Za-z0-9_]+\.js' /home/root/.cache/cog | sort -u | tr '\n' ' ')"
echo "# kiosk $(systemctl show -p NRestarts -p ActiveEnterTimestamp kiosk | tr '\n' ' ')"
POST
restore_conf

n=$(grep -c 'MP|' "$OUT")
if [ "$(live720 "$M0")" -ne 1 ] || [ "$(live720 "$M1")" -ne 1 ]; then
	echo "# VOID: 1280x720 not live before and after" >> "$OUT"; echo "VOID (display mode) -- $OUT"; exit 3
fi
[ "$n" -ge 1 ] || { echo "# NO PAYLOAD: no MP| line read back" >> "$OUT"; echo "no payload -- $OUT"; exit 1; }
echo "# complete $(date -u +%FT%TZ): $n payload line(s)" >> "$OUT"
echo "captured -> $OUT"
