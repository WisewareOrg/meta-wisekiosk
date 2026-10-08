#!/bin/bash
# run-v3-short.sh <ssh-target> <local-outdir> <n-bursts> -- the v3 capture pattern
# (run-burst-capture-v3-control.sh), generalized to a caller-chosen burst count instead of a
# fixed 12-minute run, for a feature-fix trial that only needs a handful of samples. Same
# 15-frame kiosk-drmgrab --report burst every ~60s, space-batched transfer, device-clock-paced
# scheduling.
set -u
T=${1:?ssh-target}; OUTDIR=${2:?local-outdir}; NBURSTS=${3:?n-bursts}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
INTERVAL=60
FRAMES=15

mkdir -p "$OUTDIR"
trap 'exit 1' INT TERM HUP

# check_free_space -- aborts cleanly if OUTDIR's filesystem has under 1G free. A capture
# destination that fills mid-transfer corrupts the batch silently (tar truncates, not fails
# loud) -- this is checked before every burst, not just once at the top.
check_free_space() {
	local avail_kb
	avail_kb=$(df --output=avail -k "$OUTDIR" | tail -1 | tr -d ' ')
	if [ -z "$avail_kb" ] || [ "$avail_kb" -lt 1048576 ]; then
		echo "ABORT: ${avail_kb:-unknown} KB free at $OUTDIR, below the 1G floor" >&2
		return 1
	fi
}

one_burst() {
	local label=$1 n=$2 remote_dir=/data/burst-v3s-$1-$2
	"$KSSH" "$T" "sh -s" <<REMOTE
rm -rf $remote_dir
mkdir -p $remote_dir
i=1
while [ \$i -le $FRAMES ]; do
	m=\$(printf '%03d' \$i)
	cat /proc/uptime | cut -d' ' -f1 >> $remote_dir/timestamps.txt
	printf 'FRAME %s: ' "\$m" >> $remote_dir/report.txt
	kiosk-drmgrab --report $remote_dir/frame_\$m.ppm >> $remote_dir/report.txt 2>&1
	echo \$? >> $remote_dir/rc.txt
	i=\$((i + 1))
done
REMOTE
	"$KSSH" "$T" "cd $remote_dir && tar cf - ." > "$OUTDIR/$label-$n.tar"
	mkdir -p "$OUTDIR/$label-$n"
	tar xf "$OUTDIR/$label-$n.tar" -C "$OUTDIR/$label-$n"
	rm -f "$OUTDIR/$label-$n.tar"
	"$KSSH" "$T" "rm -rf $remote_dir"
	sort -u "$OUTDIR/$label-$n/rc.txt" | tr '\n' ' '
}

for n in $(seq 1 "$NBURSTS"); do
	check_free_space || exit 1
	echo "=== burst $n/$NBURSTS $(date -u +%FT%TZ) ==="
	rc=$(one_burst control "$n")
	echo "burst $n rc: $rc"
	[ "$n" -lt "$NBURSTS" ] && sleep "$INTERVAL"
done

echo V3_SHORT_DONE
