#!/bin/bash
# run-fw-burst-capture.sh <ssh-target> <local-outdir> -- 90 kiosk-fwgrab captures back to
# back, then 90 kiosk-drmgrab --report captures back to back, each tool's captures split
# into batches of 30 to stay inside /data's free space, transferred off and deleted from
# /data before the next batch starts (same space-batching as the earlier bursts).
#
# kiosk-fwgrab has no internal timing, so each capture is timed from this script using the
# device's own monotonic clock (/proc/uptime, ~10ms resolution): a timestamp before the call
# and the elapsed ms logged alongside rc in report.txt. kiosk-drmgrab's own --report line
# (fb_before/fb_after/copy_ms) is used as-is, same as the earlier bursts.
set -u
T=${1:?ssh-target}; OUTDIR=${2:?local-outdir}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
FRAMES=90
BATCH=30

mkdir -p "$OUTDIR"

# one_fw_batch <batch-num> -- BATCH kiosk-fwgrab captures, transferred and cleaned up.
one_fw_batch() {
	local n=$1 remote_dir=/data/fwburst-fw-$1
	"$KSSH" "$T" "sh -s" <<REMOTE
rm -rf $remote_dir
mkdir -p $remote_dir
i=1
while [ \$i -le $BATCH ]; do
	m=\$(printf '%03d' \$i)
	t0=\$(cat /proc/uptime | cut -d' ' -f1)
	err=\$(kiosk-fwgrab $remote_dir/frame_\$m.ppm 2>&1)
	rc=\$?
	t1=\$(cat /proc/uptime | cut -d' ' -f1)
	ms=\$(awk -v a="\$t0" -v b="\$t1" 'BEGIN{printf "%d", (b-a)*1000}')
	echo "\$t0" >> $remote_dir/timestamps.txt
	printf 'FRAME %s: rc=%s ms=%s\n' "\$m" "\$rc" "\$ms" >> $remote_dir/report.txt
	[ -n "\$err" ] && printf 'FRAME %s stderr: %s\n' "\$m" "\$err" >> $remote_dir/report.txt
	echo \$rc >> $remote_dir/rc.txt
	i=\$((i + 1))
done
REMOTE
	"$KSSH" "$T" "cd $remote_dir && tar cf - ." > "$OUTDIR/fw-$n.tar"
	mkdir -p "$OUTDIR/fw-$n"
	tar xf "$OUTDIR/fw-$n.tar" -C "$OUTDIR/fw-$n"
	rm -f "$OUTDIR/fw-$n.tar"
	"$KSSH" "$T" "rm -rf $remote_dir"
	sort -u "$OUTDIR/fw-$n/rc.txt" | tr '\n' ' '
}

# one_drm_batch <batch-num> -- BATCH kiosk-drmgrab --report captures, transferred and cleaned up.
one_drm_batch() {
	local n=$1 remote_dir=/data/fwburst-drm-$1
	"$KSSH" "$T" "sh -s" <<REMOTE
rm -rf $remote_dir
mkdir -p $remote_dir
i=1
while [ \$i -le $BATCH ]; do
	m=\$(printf '%03d' \$i)
	cat /proc/uptime | cut -d' ' -f1 >> $remote_dir/timestamps.txt
	printf 'FRAME %s: ' "\$m" >> $remote_dir/report.txt
	kiosk-drmgrab --report $remote_dir/frame_\$m.ppm >> $remote_dir/report.txt 2>&1
	echo \$? >> $remote_dir/rc.txt
	i=\$((i + 1))
done
REMOTE
	"$KSSH" "$T" "cd $remote_dir && tar cf - ." > "$OUTDIR/drm-$n.tar"
	mkdir -p "$OUTDIR/drm-$n"
	tar xf "$OUTDIR/drm-$n.tar" -C "$OUTDIR/drm-$n"
	rm -f "$OUTDIR/drm-$n.tar"
	"$KSSH" "$T" "rm -rf $remote_dir"
	sort -u "$OUTDIR/drm-$n/rc.txt" | tr '\n' ' '
}

echo "--- fw: $FRAMES captures in batches of $BATCH ---"
batches=$((FRAMES / BATCH))
for n in $(seq 1 "$batches"); do
	echo "=== fw batch $n/$batches $(date -u +%FT%TZ) ==="
	rc=$(one_fw_batch "$n")
	echo "fw batch $n rc: $rc"
done

echo "--- drm: $FRAMES captures in batches of $BATCH ---"
for n in $(seq 1 "$batches"); do
	echo "=== drm batch $n/$batches $(date -u +%FT%TZ) ==="
	rc=$(one_drm_batch "$n")
	echo "drm batch $n rc: $rc"
done

echo FW_BURST_CAPTURE_DONE
