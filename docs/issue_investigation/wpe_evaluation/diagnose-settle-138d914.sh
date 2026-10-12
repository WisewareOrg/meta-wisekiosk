#!/bin/bash
# diagnose-settle-138d914.sh <ssh-target> -- one-shot, under the lock: read-only diagnostics on
# the current 138d914 boot that failed to settle past mean>=10, then a single kiosk restart +
# re-settle (up to 5 min), and if still under 10, a KIOSK_PROBE=1 mf-probe.js deploy to read
# module-faulted/unavailable counts from the journal. kiosk.conf is backed up before any write and
# restored (with cmp) on every exit path.
set -u
T=${1:?ssh-target}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
HERE=/home/tjwise/meta-wisekiosk-185-s2/docs/issue_investigation/wpe_evaluation
SHOT=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst/diagnose-shot.png
BACKUP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/kiosk.conf.diagnose-orig
RESTORE_PENDING=0

restore_conf() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$BACKUP"
	"$KSSH" "$T" 'rm -f /home/root/kiosk-probe.js; systemctl restart kiosk'
	AFTER="${BACKUP}.after"
	"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$AFTER"
	cmp "$BACKUP" "$AFTER" && echo "RESTORE_IDENTICAL" || echo "RESTORE_MISMATCH"
}
trap restore_conf EXIT
trap 'exit 1' INT TERM HUP

mean_of() {
	# mean_of <shot-path> -- re-reads the mean line kiosk-screenshot.sh already printed to stdout.
	sed -n 's/^min=.* mean=\([0-9.]*\)$/\1/p'
}

echo "--- read-only: buildinfo + booted slot ---"
"$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo; rauc status 2>&1 | grep -E "Booted from|Activated"'

echo "--- read-only: systemctl status kiosk ---"
"$KSSH" "$T" 'systemctl status kiosk --no-pager'

echo "--- read-only: kiosk journal, this boot ---"
"$KSSH" "$T" 'journalctl -u kiosk -b 0 --no-pager'

echo "--- read-only: uptime/load ---"
"$KSSH" "$T" 'uptime; cat /proc/loadavg'

echo "--- read-only: fresh screenshot mean ---"
rm -f "$SHOT"
SHOT_OUT=$(/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-screenshot.sh "$T" "$SHOT")
echo "$SHOT_OUT"
CUR_MEAN=$(printf '%s\n' "$SHOT_OUT" | mean_of)
echo "current full-frame mean: ${CUR_MEAN:-unknown}"

echo "--- read-only: fwgrab vs drmgrab full-frame means ---"
"$KSSH" "$T" 'sh -s' <<'REMOTE'
rm -f /tmp/diag-fw.ppm /tmp/diag-drm.ppm
kiosk-fwgrab /tmp/diag-fw.ppm 2>&1
echo "fwgrab rc=$?"
[ -f /tmp/diag-fw.ppm ] && identify -format 'fwgrab mean=%[fx:mean*255]\n' /tmp/diag-fw.ppm
kiosk-drmgrab --report /tmp/diag-drm.ppm 2>&1
echo "drmgrab rc=$?"
[ -f /tmp/diag-drm.ppm ] && identify -format 'drmgrab mean=%[fx:mean*255]\n' /tmp/diag-drm.ppm
rm -f /tmp/diag-fw.ppm /tmp/diag-drm.ppm
REMOTE

if awk -v m="${CUR_MEAN:-0}" 'BEGIN { exit !(m >= 10) }'; then
	echo "RESULT: already >=10 (${CUR_MEAN}) -- no recovery steps needed"
	exit 0
fi

echo "--- step 1: restart kiosk once, re-settle up to 5 min ---"
"$KSSH" "$T" 'systemctl restart kiosk'
RECOVERED=0
for wait in 10 20 30 40 50 60 90 120 150 180 210 240 270 300; do
	sleep 10
	rm -f "$SHOT"
	SHOT_OUT=$(/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-screenshot.sh "$T" "$SHOT")
	echo "$SHOT_OUT"
	CUR_MEAN=$(printf '%s\n' "$SHOT_OUT" | mean_of)
	echo "t=${wait}s mean=${CUR_MEAN:-unknown}"
	if awk -v m="${CUR_MEAN:-0}" 'BEGIN { exit !(m >= 10) }'; then
		RECOVERED=1
		echo "RECOVERED at t=${wait}s, mean=$CUR_MEAN"
		break
	fi
done

if [ "$RECOVERED" = 1 ]; then
	echo "RESULT: recovered after restart -- was slow to load, not faulted"
	exit 0
fi

echo "--- step 2: still <10 after restart -- deploy KIOSK_PROBE=1 mf-probe.js ---"
"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$BACKUP"
RESTORE_PENDING=1
"$KSSH" "$T" 'cat > /home/root/kiosk-probe.js' < "$HERE/mf-probe.js"
"$KSSH" "$T" 'sh -s' <<'REMOTE'
C=/data/config/kiosk.conf
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_PROBE=1' >> $C
echo "# boot-start $(cat /proc/sys/kernel/random/boot_id)"
systemctl restart kiosk
echo "# start-epoch $(date +%s)"
REMOTE

echo "--- waiting 2 min for the first MF| sample ---"
sleep 120

echo "--- MF| lines since restart ---"
"$KSSH" "$T" 'journalctl -u kiosk -b 0 -o cat --no-pager | grep "MF|"'

echo DIAGNOSE_DONE
