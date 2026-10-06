#!/bin/bash
# kiosk-stability-check.sh <ssh-target> [seconds]
#
# One soak under wpe-kiosk, judged by kiosk-stability-verdict.py against the zero
# baseline. The probe is the composite soak-cards-probe.js (mf-probe.js +
# cards-probe.js), so every 30 s sample carries both MF| (module faults) and CP|
# (cards-live). CP| is recorded, not judged: the fraction with l=4
# (parse_cards_probe.live_fraction) is reported, since a soak can legitimately cross a
# park-hours boundary.
#
# The probe deployed to /home/root/kiosk-probe.js, kiosk.conf backed up and
# KIOSK_PROBE=1 appended, wpe-kiosk's WebKit cache cleared, kiosk restarted. wpe-kiosk
# prints each title as "TITLE <title>" (MF|) and console messages reach stdout through
# WPE_KIOSK_CONSOLE (CP|), both under KIOSK_PROBE=1, so every 30 s both samples land in
# the kiosk journal. After <seconds> (default 3600) + 60 s it appends the journal's MF|
# and CP| lines since the start, kiosk-soak --summary over the samples taken since the
# start and those samples themselves, kiosk NRestarts, boot id and /proc/vmstat
# pswpin/pswpout at both ends, /proc/pressure/memory, and kernel OOM lines since the
# start; then it restores kiosk.conf, removes the probe and restarts kiosk. Before
# deploy, a pre-run screenshot must show the rendered dashboard (mean luma >= 10 within
# 120 s), and the cache dir must exist and hold an entry (kiosk-cache.sh's
# require_kiosk_cache). A kiosk.conf backup already on the board means an earlier run
# did not restore; the run refuses and leaves it alone.
#
# The verdict's inputs: restarts, the NRestarts change across the soak, or the end
# value when the boot id changed (NRestarts starts at 0 on each boot); reboots, 1 when
# the boot id changed; OOM-killer lines, counted, any one of them a memory problem.
# Swap, RSS and PSI are printed, not judged.
#
# Everything is written to stdout. Exit: kiosk-stability-verdict.py's 0 (no
# regression), 1 (regression) or 2 (could not tell); also 2 on no rendered dashboard,
# an absent or empty cache, a kiosk.conf backup already present, a failed deploy or
# start, or a misinvocation.
set -u
T=${1:-}; SECS=${2:-3600}
[ -n "$T" ] || { echo "usage: kiosk-stability-check.sh <ssh-target> [seconds]" >&2; exit 2; }
[[ $SECS =~ ^[0-9]+$ ]] || { echo "seconds '$SECS' is not a count" >&2; exit 2; }
HERE=$(dirname "$(readlink -f "$0")")
KSSH=$HERE/kiosk-ssh.sh
PROBE=$HERE/soak-cards-probe.js
# shellcheck source=kiosk-cache.sh
. "$HERE/kiosk-cache.sh"
WORK=$(mktemp -d) || { echo "could not tell: no local work directory" >&2; exit 2; }
OUT=$WORK/capture.txt
SHOT=$WORK/pre-run.png
: > "$OUT"
# shellcheck source=kiosk-probe-run.sh
. "$HERE/kiosk-probe-run.sh"

# kiosk.conf is restored on any exit once this run has backed it up, interrupts included;
# the capture is then printed and the work directory removed.
trap finish EXIT
trap 'exit 2' INT TERM HUP

settle_dashboard

require_kiosk_cache "$KSSH" "$T"

{
echo "# kiosk-stability-check.sh secs=$SECS"
echo "# harness $(git -C "$HERE" rev-parse HEAD)$(git -C "$HERE" diff --quiet HEAD -- . || echo " DIRTY")"
echo "# started $(date -u +%FT%TZ)"
echo "# probe sha256 local    $(sha256sum < "$PROBE" | cut -d' ' -f1)"
} >> "$OUT"
"$KSSH" "$T" 'cat > /home/root/kiosk-probe.js' < "$PROBE" || { echo "# DEPLOY FAILED" >> "$OUT"; exit 2; }
RESTORE_PENDING=1
{ printf '%s\n' "$KIOSK_CACHE_FN" "$KIOSK_PROBE_DEPLOY_FN"; cat <<'EOF'; } | "$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1
deploy_probe_conf
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
echo "# probe sha256 deployed $(sha256sum < /home/root/kiosk-probe.js | cut -d' ' -f1)"
echo "# boot-start $(cat /proc/sys/kernel/random/boot_id)"
clear_kiosk_cache
systemctl restart kiosk
echo "# start-epoch $(date +%s) $(systemctl show -p NRestarts kiosk)"
echo "# vmstat-start $(grep -E '^(pswpin|pswpout) ' /proc/vmstat | tr '\n' ' ')"
EOF
rc=$?
[ $rc -eq 3 ] && RESTORE_PENDING=0
[ $rc -eq 0 ] || exit 2
START=$(sed -n 's/^# start-epoch \([0-9]*\).*/\1/p' "$OUT")
[ -n "$START" ] || { echo "# START FAILED" >> "$OUT"; exit 2; }

sleep $((SECS + 60))

"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<EOF
echo "=== journal MF| since start-epoch ==="
journalctl -u kiosk --since @$START -o cat --no-pager | grep 'MF|'
echo "=== journal CP| since start-epoch ==="
journalctl -u kiosk --since @$START -o cat --no-pager | grep 'CP|'
echo "=== kiosk-soak samples since start-epoch ==="
awk -v s=$START '{ split(\$1, a, "="); if (a[2] >= s) print }' /data/kiosk-soak.log
N=\$(awk -v s=$START '{ split(\$1, a, "="); if (a[2] >= s) n++ } END { print n + 0 }' /data/kiosk-soak.log)
echo "=== kiosk-soak --summary \$N (samples since start-epoch) ==="
[ "\$N" -gt 0 ] && kiosk-soak.sh --summary "\$N"
echo "# boot-end \$(cat /proc/sys/kernel/random/boot_id)"
echo "# end \$(systemctl show -p NRestarts kiosk)"
echo "# vmstat-end \$(grep -E '^(pswpin|pswpout) ' /proc/vmstat | tr '\n' ' ')"
echo "=== /proc/pressure/memory ==="
cat /proc/pressure/memory
echo "=== kernel OOM lines since start-epoch ==="
journalctl -k --since @$START --no-pager | grep -iE 'out of memory|oom-kill|oom_reaper'
echo "=== end of kernel OOM lines ==="
EOF
restore_conf

CP_LINES=$(grep 'CP|' "$OUT")
if [ -n "$CP_LINES" ]; then
	FRAC=$(printf '%s\n' "$CP_LINES" | python3 -c '
import sys
sys.path.insert(0, "'"$HERE"'")
import parse_cards_probe as pcp
print(f"{pcp.live_fraction(sys.stdin.read().splitlines()):.3f}")
')
	echo "# cards-live fraction (l=4): $FRAC ($(printf '%s\n' "$CP_LINES" | wc -l) CP| samples)" >> "$OUT"
else
	echo "# cards-live: no CP| samples read back" >> "$OUT"
fi

b0=$(sed -n 's/^# boot-start //p' "$OUT")
b1=$(sed -n 's/^# boot-end //p' "$OUT")
n0=$(sed -n 's/^# start-epoch [0-9]* NRestarts=\([0-9]*\)$/\1/p' "$OUT")
n1=$(sed -n 's/^# end NRestarts=\([0-9]*\)$/\1/p' "$OUT")
if [ -z "$b0" ] || [ -z "$b1" ] || [ -z "$n0" ] || [ -z "$n1" ]; then
	echo "# could not tell: boot id or NRestarts not read at both ends" >> "$OUT"; exit 2
fi
if [ "$b0" = "$b1" ]; then reboots=0; restarts=$((n1 - n0)); else reboots=1; restarts=$n1; fi
oom=$(sed -n '/^=== kernel OOM lines since start-epoch ===$/,/^=== end of kernel OOM lines ===$/p' "$OUT" | grep -vc '^===')

python3 "$HERE/kiosk-stability-verdict.py" "$OUT" "$restarts" "$reboots" "$oom" "$SECS" > "$WORK/verdict.txt" 2>&1
rc=$?
{ echo "# restarts=$restarts reboots=$reboots oom-lines=$oom"; echo "=== kiosk-stability-verdict.py ==="; cat "$WORK/verdict.txt"; } >> "$OUT"
exit $rc
