#!/bin/bash
# run-burst-capture-v2.sh <ssh-target> <local-outdir> -- v2 of run-burst-capture.sh, with
# kiosk-drmgrab --report (one stderr line "fb_before=<id> fb_after=<id> copy_ms=<int>" per
# successful capture). Control: 60 frames. CPU rendering: 120 frames in two 60-frame batches
# (space-batched transfer-then-delete, same as v1), capped at ~3 min total CPU-rendering window.
# Does NOT touch /data/update.raucb -- that's the OTA tool's own business, not this script's.
set -u
T=${1:?ssh-target}; OUTDIR=${2:?local-outdir}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
BACKUP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/kiosk.conf.burst-v2-orig
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

# burst_batch <label> <batch-suffix> <n-frames> -- one capture batch, transferred and cleaned up
# before returning. report.txt gets one line per frame, prefixed "FRAME <n>:", holding whatever
# kiosk-drmgrab --report wrote to stderr for that frame (the report line on success, or its
# failure message otherwise) -- so the analysis script can align by position even on a failure.
burst_batch() {
	local label=$1 suffix=$2 n=$3 remote_dir=/data/burst-$1-$2
	echo "--- $label/$suffix: $n-frame batch ---"
	"$KSSH" "$T" "sh -s" <<REMOTE
rm -rf $remote_dir
mkdir -p $remote_dir
i=1
while [ \$i -le $n ]; do
	m=\$(printf '%03d' \$i)
	cat /proc/uptime | cut -d' ' -f1 >> $remote_dir/timestamps.txt
	printf 'FRAME %s: ' "\$m" >> $remote_dir/report.txt
	kiosk-drmgrab --report $remote_dir/frame_\$m.ppm >> $remote_dir/report.txt 2>&1
	echo \$? >> $remote_dir/rc.txt
	i=\$((i + 1))
done
REMOTE
	echo "--- $label/$suffix: transfer off device ---"
	"$KSSH" "$T" "cd $remote_dir && tar cf - ." > "$OUTDIR/$label-$suffix.tar"
	mkdir -p "$OUTDIR/$label-$suffix"
	tar xf "$OUTDIR/$label-$suffix.tar" -C "$OUTDIR/$label-$suffix"
	rm -f "$OUTDIR/$label-$suffix.tar"
	echo "--- $label/$suffix: clean up on-device copies ---"
	"$KSSH" "$T" "rm -rf $remote_dir"
	echo "--- $label/$suffix: rc summary ---"
	sort -u "$OUTDIR/$label-$suffix/rc.txt" | tr '\n' ' '; echo
}

echo "--- control: settle 20s ---"
sleep 20
burst_batch control 1 60

echo "--- switch to CPU rendering, restart ---"
"$KSSH" "$T" 'printf "KIOSK_INSPECTOR=0\nWEBKIT_SKIA_ENABLE_CPU_RENDERING=1\n" > /data/config/kiosk.conf; systemctl restart kiosk'
echo "--- cpu: settle 20s ---"
sleep 20
burst_batch cpu 1 60
burst_batch cpu 2 60

echo "--- restore kiosk.conf ---"
restore_conf
"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "${BACKUP}.after"
cmp "$BACKUP" "${BACKUP}.after" && echo RESTORE_IDENTICAL || echo RESTORE_MISMATCH

echo "--- confirm dashboard normal ---"
SHOT="$OUTDIR/after-restore.png"
rm -f "$SHOT"
/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-screenshot.sh "$T" "$SHOT"
echo "screenshot rc=$?"

echo BURST_CAPTURE_V2_DONE
