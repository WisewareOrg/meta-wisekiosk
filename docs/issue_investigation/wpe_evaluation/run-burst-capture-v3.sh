#!/bin/bash
# run-burst-capture-v3.sh <ssh-target> <local-outdir> -- v3: long-session periodic sampling.
# Control (default 2.54, image 449e571) for 12 min, then CPU rendering for 12 min (owner OK'd the
# flashing). In each: a 15-frame kiosk-drmgrab --report burst every ~60s (12 bursts/run), each
# transferred off and deleted from /data before the next burst starts (space-batched, same as v1
# and v2). Confirms WEBKIT_SKIA_ENABLE_CPU_RENDERING actually reached cog's and WPEWebProcess's
# own environment (grep /proc/<pid>/environ for both) right after the CPU-rendering restart, and
# logs it. Same EXIT/TERM restore trap as v1/v2.
set -u
T=${1:?ssh-target}; OUTDIR=${2:?local-outdir}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
BACKUP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/kiosk.conf.burst-v3-orig
DURATION=720      # 12 min per run
INTERVAL=60       # seconds between burst starts
FRAMES=15         # frames per burst
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

echo "--- switch to CPU rendering, restart ---"
"$KSSH" "$T" 'printf "KIOSK_INSPECTOR=0\nWEBKIT_SKIA_ENABLE_CPU_RENDERING=1\n" > /data/config/kiosk.conf; systemctl restart kiosk'
sleep 20

echo "--- confirm env reached cog and WPEWebProcess ---"
"$KSSH" "$T" 'sh -s' <<'REMOTE'
for name in cog WPEWebProcess; do
	pid=$(pidof "$name" | cut -d" " -f1)
	if [ -n "$pid" ]; then
		echo "$name pid=$pid:"
		tr '\0' '\n' < /proc/$pid/environ | grep WEBKIT_SKIA_ENABLE_CPU_RENDERING || echo "  (not found in environ)"
	else
		echo "$name: no pid"
	fi
done
REMOTE

echo "--- cpu rendering: $((DURATION/60)) min, burst every ${INTERVAL}s ---"
run_bursts cpu

echo "--- restore kiosk.conf ---"
restore_conf
"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "${BACKUP}.after"
cmp "$BACKUP" "${BACKUP}.after" && echo RESTORE_IDENTICAL || echo RESTORE_MISMATCH

echo "--- confirm dashboard normal ---"
SHOT="$OUTDIR/after-restore.png"
rm -f "$SHOT"
/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-screenshot.sh "$T" "$SHOT"
echo "screenshot rc=$?"

echo BURST_CAPTURE_V3_DONE
