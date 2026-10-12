#!/bin/bash
# run-load-experiment.sh <ssh-target> <local-outdir> <image-label> -- three-phase CPU-contention
# experiment: does the flashing track CPU load rather than which capture tool is reading the
# scanout. Each phase is 90 kiosk-fwgrab captures back to back (batches of 30, space-batched and
# transferred off as in the other fw bursts; timed externally via /proc/uptime, as fwgrab has no
# internal timer):
#
#   idle    -- no added load.
#   spinner -- a tight `while :; do :; done` busy-loop running on the device for the phase.
#   drmloop -- a `kiosk-drmgrab --report` loop running concurrently for the phase (the same kind
#              of CPU/IO load the earlier drmgrab bursts put on the device, but discarded output;
#              only the fwgrab captures taken alongside it are analysed).
#
# The load process is started detached (`setsid ... &`, redirected, so it survives the ssh
# session that started it) and its pid captured from the backgrounding shell's $!. It is killed
# by pid after the phase, and also on any abort via the EXIT trap -- a dead experiment must never
# leave a spinner or a capture loop running on the board.
set -u
T=${1:?ssh-target}; OUTDIR=${2:?local-outdir}; IMG=${3:?image-label}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
FRAMES=90
BATCH=30
LOAD_PID=""

kill_load() {
	[ -n "$LOAD_PID" ] || return 0
	"$KSSH" "$T" "kill -9 $LOAD_PID >/dev/null 2>&1; true"
	LOAD_PID=""
}
trap kill_load EXIT
trap 'exit 1' INT TERM HUP

mkdir -p "$OUTDIR"

# one_fw_batch <phase> <batch-num> -- BATCH kiosk-fwgrab captures, transferred and cleaned up.
one_fw_batch() {
	local phase=$1 n=$2 remote_dir=/data/loadexp-$IMG-$1-$2
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
	"$KSSH" "$T" "cd $remote_dir && tar cf - ." > "$OUTDIR/$phase-$n.tar"
	mkdir -p "$OUTDIR/$phase-$n"
	tar xf "$OUTDIR/$phase-$n.tar" -C "$OUTDIR/$phase-$n"
	rm -f "$OUTDIR/$phase-$n.tar"
	"$KSSH" "$T" "rm -rf $remote_dir"
	sort -u "$OUTDIR/$phase-$n/rc.txt" | tr '\n' ' '
}

run_phase() {
	local phase=$1
	local batches=$((FRAMES / BATCH))
	for n in $(seq 1 "$batches"); do
		echo "=== $phase batch $n/$batches $(date -u +%FT%TZ) ==="
		local rc
		rc=$(one_fw_batch "$phase" "$n")
		echo "$phase batch $n rc: $rc"
	done
}

# start_load <remote-command> -- detaches it (setsid, redirected so it outlives the ssh
# session), returns its pid via LOAD_PID, and verifies it is actually running: a backgrounded ssh
# command can read back as a nonzero/garbage result even when the remote process is fine, so the
# pid is confirmed with a separate query rather than trusted from the launch call's exit status.
start_load() {
	local remote_cmd=$1
	LOAD_PID=$("$KSSH" "$T" "setsid sh -c '$remote_cmd' >/dev/null 2>&1 & echo \$!" | tr -dc '0-9')
	sleep 1
	if [ -z "$LOAD_PID" ] || ! "$KSSH" "$T" "kill -0 $LOAD_PID 2>/dev/null"; then
		echo "ABORT: load process did not start or is not running (pid='$LOAD_PID')"
		LOAD_PID=""
		return 1
	fi
	echo "load pid=$LOAD_PID confirmed running"
}

echo "--- phase A: idle ---"
run_phase idle

echo "--- phase B: CPU spinner ---"
start_load 'while :; do :; done' || exit 1
run_phase spinner
kill_load

echo "--- phase C: concurrent drmgrab loop ---"
start_load 'while :; do kiosk-drmgrab --report /tmp/loadgrab.ppm >/dev/null 2>&1; done' || exit 1
run_phase drmloop
kill_load
"$KSSH" "$T" 'rm -f /tmp/loadgrab.ppm'

echo LOAD_EXPERIMENT_DONE
