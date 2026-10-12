#!/bin/bash
# run-burst-capture.sh <ssh-target> <local-outdir> -- confirms/refutes the stale-buffer
# hypothesis for WEBKIT_SKIA_ENABLE_CPU_RENDERING=1's visible flashing. Captures a 60-frame
# back-to-back kiosk-drmgrab burst under the default 2.54 config (control), then the same burst
# under CPU rendering, then restores kiosk.conf. kiosk-drmgrab prints no fb id/buffer handle on
# success (checked against its source, meta-wisekiosk/recipes-graphics/kiosk-drmgrab/files/
# kiosk-drmgrab.c) -- not patched, so this capture carries no per-frame buffer-handle data, only
# the PPM content itself and a per-frame monotonic timestamp read on the board.
set -u
T=${1:?ssh-target}; OUTDIR=${2:?local-outdir}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
BACKUP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/kiosk.conf.burst-orig
RESTORE_PENDING=0

mkdir -p "$OUTDIR"

restore_conf() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$BACKUP"
	"$KSSH" "$T" 'systemctl restart kiosk'
}
trap restore_conf EXIT
trap 'exit 1' INT TERM HUP

echo "--- R1 header ---"
"$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo; grep "^meta-webkit " /etc/buildinfo; rauc status 2>&1 | grep "Booted from"'

echo "--- backup kiosk.conf ---"
"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$BACKUP"
cat "$BACKUP"
RESTORE_PENDING=1

burst() {
	local label=$1 remote_dir=/data/burst-$1
	echo "--- $label: settle 20s ---"
	sleep 20
	echo "--- $label: 60-frame burst ---"
	"$KSSH" "$T" "sh -s" <<REMOTE
rm -rf $remote_dir
mkdir -p $remote_dir
i=1
while [ \$i -le 60 ]; do
	n=\$(printf '%03d' \$i)
	cat /proc/uptime | cut -d' ' -f1 >> $remote_dir/timestamps.txt
	kiosk-drmgrab $remote_dir/frame_\$n.ppm 2>> $remote_dir/errors.txt
	echo \$? >> $remote_dir/rc.txt
	i=\$((i + 1))
done
REMOTE
	echo "--- $label: transfer off device ---"
	"$KSSH" "$T" "cd $remote_dir && tar cf - ." > "$OUTDIR/$label.tar"
	mkdir -p "$OUTDIR/$label"
	tar xf "$OUTDIR/$label.tar" -C "$OUTDIR/$label"
	rm -f "$OUTDIR/$label.tar"
	echo "--- $label: clean up on-device copies ---"
	"$KSSH" "$T" "rm -rf $remote_dir"
	echo "--- $label: rc summary ---"
	sort -u "$OUTDIR/$label/rc.txt" | tr '\n' ' '; echo
}

burst control

echo "--- switch to CPU rendering, restart ---"
"$KSSH" "$T" 'printf "KIOSK_INSPECTOR=0\nWEBKIT_SKIA_ENABLE_CPU_RENDERING=1\n" > /data/config/kiosk.conf; systemctl restart kiosk'

burst cpu

echo "--- restore kiosk.conf ---"
restore_conf
"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "${BACKUP}.after"
cmp "$BACKUP" "${BACKUP}.after" && echo RESTORE_IDENTICAL || echo RESTORE_MISMATCH

echo "--- confirm dashboard normal ---"
SHOT="$OUTDIR/after-restore.png"
rm -f "$SHOT"
/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-screenshot.sh "$T" "$SHOT"
echo "screenshot rc=$?"

echo BURST_CAPTURE_DONE
