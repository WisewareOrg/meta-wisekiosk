#!/bin/bash
# run-feature-trial.sh <ssh-target> <features-value|UNSET> <local-outdir> -- one fix trial
# (or a same-session baseline, when features-value is the literal string UNSET): back up
# kiosk.conf, set KIOSK_COG_FEATURES=<features-value> (or leave it absent for UNSET), restart
# kiosk, confirm cog's own argv matches, settle (mean>=10, up to 20 min -- the slow-load finding
# means the old 5 min budget false-VOIDs a healthy board), then 6 v3 bursts (kiosk-drmgrab
# --report) AND one 90-frame kiosk-fwgrab burst (batched by 30, space-freed between batches),
# then both analyses (analyze_burst_v3.py tile-grid, analyze_fw_burst.py flips). kiosk.conf is
# restored (cmp-verified) regardless of outcome.
#
# Exit codes: 0 settled and captured; 3 VOID -- cog did not come up matching the requested
# features (restart loop or rejected flag); 4 VOID -- it stayed up but never settled past the
# screenshot gate within 20 min.
set -u
T=${1:?ssh-target}; FEATURES=${2:?features-value-or-UNSET}; OUTDIR=${3:?local-outdir}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
BURST=$(dirname "$(readlink -f "$0")")
SHOT="$OUTDIR/settle.png"
BACKUP="$OUTDIR/kiosk.conf.orig"
RESTORE_PENDING=0

mkdir -p "$OUTDIR"

restore_conf() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$BACKUP"
	"$KSSH" "$T" 'systemctl restart kiosk'
	"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "${BACKUP}.after"
	cmp "$BACKUP" "${BACKUP}.after" && echo "RESTORE_IDENTICAL" || echo "RESTORE_MISMATCH"
}
trap restore_conf EXIT
trap 'exit 1' INT TERM HUP

echo "--- trial: KIOSK_COG_FEATURES=$FEATURES ---"
"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$BACKUP"
RESTORE_PENDING=1
if [ "$FEATURES" = "UNSET" ]; then
	"$KSSH" "$T" 'systemctl restart kiosk'
else
	"$KSSH" "$T" "sh -s" <<REMOTE
C=/data/config/kiosk.conf
[ -s \$C ] && [ -n "\$(tail -c 1 \$C)" ] && echo >> \$C
echo 'KIOSK_COG_FEATURES=$FEATURES' >> \$C
systemctl restart kiosk
REMOTE
fi

echo "--- confirm cog's argv (checked 3x over 15s) ---"
STABLE=0
for i in 1 2 3; do
	sleep 5
	ACTIVE=$("$KSSH" "$T" 'systemctl is-active kiosk')
	ARGV=$("$KSSH" "$T" 'pid=$(pidof cog | cut -d" " -f1); [ -n "$pid" ] && tr "\0" " " < /proc/$pid/cmdline')
	echo "check $i: active=$ACTIVE argv=[$ARGV]"
	OK=0
	if [ "$ACTIVE" = "active" ]; then
		if [ "$FEATURES" = "UNSET" ]; then
			printf '%s' "$ARGV" | grep -q -- '--features=' || OK=1
		else
			printf '%s' "$ARGV" | grep -qF -- "--features=$FEATURES" && OK=1
		fi
	fi
	if [ "$OK" = 1 ]; then STABLE=$((STABLE + 1)); else STABLE=0; fi
done
if [ "$STABLE" -lt 3 ]; then
	echo "VOID: cog did not stay up with the expected argv -- restart loop or rejected flag"
	exit 3
fi

echo "--- settle (mean>=10, up to 20 min) ---"
RECOVERED=0
SETTLE_START=$(date +%s)
for i in $(seq 1 120); do
	if [ "$i" -gt 1 ]; then rm -f "$SHOT"; sleep 10; fi
	SHOT_OUT=$(/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-screenshot.sh "$T" "$SHOT")
	echo "$SHOT_OUT"
	MEAN=$(printf '%s\n' "$SHOT_OUT" | sed -n 's/^min=.* mean=\([0-9.]*\)$/\1/p')
	elapsed=$(( $(date +%s) - SETTLE_START ))
	if awk -v m="${MEAN:-0}" 'BEGIN { exit !(m >= 10) }'; then
		RECOVERED=1
		echo "settled at t=${elapsed}s, mean=$MEAN"
		break
	fi
done
if [ "$RECOVERED" != 1 ]; then
	echo "VOID: did not settle past mean>=10 within 20 min"
	exit 4
fi

echo "--- 6 v3 bursts ---"
"$BURST/run-v3-short.sh" "$T" "$OUTDIR/v3" 6
V3_RC=$?
[ $V3_RC -eq 0 ] || { echo "ABORT: v3 capture failed rc=$V3_RC"; exit 1; }

echo "--- 90-frame fwgrab burst (batched by 30) ---"
FWDIR="$OUTDIR/fw"
mkdir -p "$FWDIR"
for n in 1 2 3; do
	avail_kb=$(df --output=avail -k "$FWDIR" | tail -1 | tr -d ' ')
	if [ -z "$avail_kb" ] || [ "$avail_kb" -lt 1048576 ]; then
		echo "ABORT: ${avail_kb:-unknown} KB free at $FWDIR, below the 1G floor"
		exit 1
	fi
	remote_dir=/data/trial-fw-$n
	"$KSSH" "$T" "sh -s" <<REMOTE
rm -rf $remote_dir
mkdir -p $remote_dir
i=1
while [ \$i -le 30 ]; do
	m=\$(printf '%03d' \$i)
	t0=\$(cat /proc/uptime | cut -d' ' -f1)
	err=\$(kiosk-fwgrab $remote_dir/frame_\$m.ppm 2>&1)
	rc=\$?
	t1=\$(cat /proc/uptime | cut -d' ' -f1)
	ms=\$(awk -v a="\$t0" -v b="\$t1" 'BEGIN{printf "%d", (b-a)*1000}')
	printf 'FRAME %s: rc=%s ms=%s\n' "\$m" "\$rc" "\$ms" >> $remote_dir/report.txt
	[ -n "\$err" ] && printf 'FRAME %s stderr: %s\n' "\$m" "\$err" >> $remote_dir/report.txt
	echo \$rc >> $remote_dir/rc.txt
	i=\$((i + 1))
done
REMOTE
	"$KSSH" "$T" "cd $remote_dir && tar cf - ." > "$FWDIR/fw-$n.tar"
	mkdir -p "$FWDIR/fw-$n"
	tar xf "$FWDIR/fw-$n.tar" -C "$FWDIR/fw-$n"
	rm -f "$FWDIR/fw-$n.tar"
	"$KSSH" "$T" "rm -rf $remote_dir"
	echo "fw batch $n rc: $(sort -u "$FWDIR/fw-$n/rc.txt" | tr '\n' ' ')"
done

echo "--- v3 tile-grid analysis ---"
dirs=$(ls -d "$OUTDIR/v3"/control-*/ 2>/dev/null | sort -V)
python3 "$BURST/analyze_burst_v3.py" "trial" $dirs

echo "--- fw flip analysis ---"
fwdirs=$(ls -d "$FWDIR"/fw-*/ 2>/dev/null | sort -V)
python3 "$BURST/analyze_fw_burst.py" "trial" fw $fwdirs

echo FEATURE_TRIAL_DONE
