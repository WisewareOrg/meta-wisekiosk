#!/bin/bash
# run-stale-diag-series.sh <ssh-target> <local-outdir> -- reproduces kiosk-render-check.sh's own
# 30-capture series EXACTLY (same kiosk-drmgrab --report calls, ~2s spacing via `sleep 2` between
# captures, batches of 5, same manifest.txt format for kiosk-render-check-stale.py) but keeps
# every PPM and the full report/manifest under <local-outdir> instead of a mktemp dir the tool
# deletes on exit -- for diagnosing a run where the live render-check verdict and the independent
# v3 burst analysis disagreed (R2: the harness is this file, committed beside the others).
set -u
T=${1:?ssh-target}; OUTDIR=${2:?local-outdir}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
SERIES=30
BATCH=5
REMOTE=/tmp/stale-diag-series.$$

mkdir -p "$OUTDIR"
: > "$OUTDIR/manifest.txt"
: > "$OUTDIR/report.txt"
trap 'exit 1' INT TERM HUP

for ((first = 1; first <= SERIES; first += BATCH)); do
	last=$((first + BATCH - 1))
	# shellcheck disable=SC2029
	out=$("$KSSH" "$T" "R=$REMOTE FIRST=$first LAST=$last sh -s" <<'SERIES'
mkdir -p "$R" || exit 1
i=$FIRST
while [ "$i" -le "$LAST" ]; do
	[ "$i" -gt 1 ] && sleep 2
	rep=$(kiosk-drmgrab --report "$R/$i.ppm" 2>&1)
	rc=$?
	echo "series $i rc=$rc $(printf '%s' "$rep" | tr '\n' ' ')"
	i=$((i + 1))
done
SERIES
)
	rc=$?
	printf '%s\n' "$out" | tee -a "$OUTDIR/report.txt" | sed 's/^/  /'
	[ $rc -eq 0 ] || { echo "ABORT: series batch $first-$last: ssh exited $rc"; exit 2; }

	names=()
	for ((i = first; i <= last; i++)); do
		line=$(printf '%s\n' "$out" | grep "^series $i rc=")
		if ! [[ $line =~ ^series\ $i\ rc=0\ fb_before=([0-9]+)\ fb_after=([0-9]+)\ copy_ms=[0-9]+\ ?$ ]]; then
			echo "ABORT: series capture $i failed: ${line:-no line returned}"
			exit 2
		fi
		echo "fb_before=${BASH_REMATCH[1]} fb_after=${BASH_REMATCH[2]} ppm=$OUTDIR/$i.ppm" >> "$OUTDIR/manifest.txt"
		names+=("$i.ppm")
	done

	# shellcheck disable=SC2029
	"$KSSH" "$T" "cd $REMOTE && tar cf - ${names[*]}" | tar xf - -C "$OUTDIR"
	fetch=("${PIPESTATUS[@]}")
	if [ "${fetch[0]}" -ne 0 ] || [ "${fetch[1]}" -ne 0 ]; then
		echo "ABORT: series batch $first-$last fetch failed (ssh ${fetch[0]}, tar ${fetch[1]})"
		exit 2
	fi
done
"$KSSH" "$T" "rm -rf $REMOTE"

echo "--- kiosk-render-check-stale.py verdict over this kept series ---"
python3 /home/tjwise/meta-wisekiosk-185-impl/tools/kiosk-render-check-stale.py "$OUTDIR/manifest.txt"
echo "stale-check rc=$?"

echo STALE_DIAG_SERIES_DONE
