#!/bin/bash
# run-burst-capture-v3-control.sh <ssh-target> <local-outdir> -- v3 capture, CONTROL phase only
# (default config, no Skia env), for a reference image. 12 min, 15-frame kiosk-drmgrab --report
# burst every ~60s (12 bursts), each transferred off and deleted from /data before the next
# burst starts, same as the two-phase v3 script this is extracted from. No kiosk.conf switch is
# made, so the EXIT/TERM trap only needs to guard against leaving the config touched if a future
# caller changes that -- today it is a no-op restore since nothing here writes kiosk.conf.
set -u
T=${1:?ssh-target}; OUTDIR=${2:?local-outdir}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
DURATION=720      # 12 min
INTERVAL=60       # seconds between burst starts
FRAMES=15         # frames per burst

mkdir -p "$OUTDIR"
trap 'exit 1' INT TERM HUP

echo "--- R1 header ---"
"$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo; grep "^meta-webkit " /etc/buildinfo; rauc status 2>&1 | grep "Booted from"; cat /data/config/kiosk.conf'

# one_burst <label> <burst-num> -- FRAMES-frame --report burst, transferred and cleaned up.
one_burst() {
	local label=$1 n=$2 remote_dir=/data/burst-v3-$1-$2
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

# run_bursts <label> -- DURATION/INTERVAL bursts at ~INTERVAL spacing, measured by the device's
# own monotonic clock (uptime) so capture+transfer time doesn't drift the schedule.
run_bursts() {
	local label=$1
	local start
	start=$("$KSSH" "$T" 'cat /proc/uptime' | cut -d' ' -f1)
	local n=0
	local elapsed=0
	while awk -v e="$elapsed" -v d="$DURATION" 'BEGIN{exit !(e<d)}'; do
		n=$((n + 1))
		echo "=== $label burst $n starting (elapsed ${elapsed}s) $(date -u +%FT%TZ) ==="
		local burst_start now rc
		burst_start=$(date +%s.%N)
		rc=$(one_burst "$label" "$n")
		echo "$label burst $n rc: $rc"
		now=$(date +%s.%N)
		local took
		took=$(awk -v a="$burst_start" -v b="$now" 'BEGIN{printf "%.1f", b-a}')
		local wait
		wait=$(awk -v t="$took" -v i="$INTERVAL" 'BEGIN{w=i-t; if (w<0) w=0; printf "%.1f", w}')
		echo "$label burst $n took ${took}s, sleeping ${wait}s"
		sleep "$wait"
		local nowup
		nowup=$("$KSSH" "$T" 'cat /proc/uptime' | cut -d' ' -f1)
		elapsed=$(awk -v s="$start" -v n="$nowup" 'BEGIN{printf "%.1f", n-s}')
	done
	echo "=== $label: $n bursts over ${elapsed}s ==="
}

echo "--- control: $((DURATION/60)) min, burst every ${INTERVAL}s ---"
run_bursts control

echo BURST_CAPTURE_V3_CONTROL_DONE
