#!/bin/bash
# run-s4-soak.sh <ssh-target> <role> <out>
#
# run-soak.sh, for S4, with cards-live recording added: the probe is the composite
# soak-cards-probe.js (mf-probe.js + cards-probe.js, bytes unchanged in each half), so every 30s
# sample carries both MF| (module faults) and CP| (cards-live). Unlike the smoothness gate, the
# soak does NOT VOID on a short sample -- it records every CP| sample and reports the fraction
# with l=4 (parse_cards_probe.live_fraction), since an hour is long enough to legitimately cross
# a park-hours boundary mid-run.
#
# The 1 h soak under cog: the composite probe deployed to /home/root/kiosk-probe.js, kiosk.conf
# backed up and KIOSK_PROBE=1 appended, cog's cache cleared, kiosk restarted. cog prints each
# title as "TITLE <title>" (MF|) and console.log reaches stdout under
# --enable-write-console-messages-to-stdout (CP|, bundled with KIOSK_PROBE=1), so every 30 s both
# samples land in the kiosk journal. After 3600 s + 60 s it appends the journal's MF| and CP|
# lines since the start, kiosk-soak --summary over the samples taken since the start and those
# samples themselves, kiosk NRestarts, boot id and /proc/vmstat pswpin/pswpout at both ends,
# /proc/pressure/memory, and kernel OOM lines since the start; then it restores kiosk.conf,
# removes the probe and restarts kiosk. A kiosk.conf backup already on the board means an earlier
# run did not restore; the run refuses, exit 1, and leaves it alone. Before deploy, the pre-run
# screenshot settle of run-smoothness.sh (mean luma >= 10 within 120 s, kept in local/), then
# cog's cache dir absent or empty is VOID, exit 3 (cog-cache.sh's require_cog_cache).
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; OUT=${3:?out}
SECS=3600
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
KSSH=$ROOT/tools/kiosk-ssh.sh
# shellcheck source-path=SCRIPTDIR source=cog-cache.sh
. "$HERE/cog-cache.sh"
SHOT=$ROOT/local/wpe-pre-$(basename "$OUT" .txt).png
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture" >&2; exit 2; }

# kiosk.conf is restored on any exit once this run has backed it up, interrupts included.
RESTORE_PENDING=0
restore_conf() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	{ printf '%s\n' "$COG_CACHE_FN"; cat <<'RESTORE'; } | "$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1
C=/data/config/kiosk.conf
if [ -f $C.wpe-bak ]; then mv $C.wpe-bak $C; elif [ -e $C.wpe-absent ]; then rm -f $C $C.wpe-absent; else echo "# NO BACKUP -- kiosk.conf left as found"; fi
rm -f /home/root/kiosk-probe.js
clear_cog_cache
systemctl restart kiosk
n=$(grep -c '^KIOSK_PROBE' $C 2>/dev/null)
echo "# restored: kiosk.conf KIOSK_PROBE lines ${n:-none, file absent}, kiosk restarted"
RESTORE
}
trap restore_conf EXIT
trap 'exit 1' INT TERM HUP

for wait in 0 10 20 30 40 50 60 70 80 90 100 110 120; do
	[ "$wait" -gt 0 ] && { rm -f "$SHOT"; sleep 10; }
	shot=$("$ROOT/tools/kiosk-screenshot.sh" "$T" "$SHOT")
	rc=$?
	printf '%s\n' "$shot"
	mean=$(printf '%s\n' "$shot" | sed -n 's/^min=.* mean=\([0-9.]*\)$/\1/p')
	[ $rc -eq 0 ] && awk -v m="${mean:-0}" 'BEGIN { exit !(m >= 10) }' && break
	[ "$wait" -eq 120 ] && { echo "VOID: pre-run screenshot not a rendered dashboard after 120 s (last mean ${mean:-none}, rc $rc) -- $SHOT" >&2; exit 3; }
done

require_cog_cache "$KSSH" "$T"

{
echo "# run-s4-soak.sh role=$ROLE secs=$SECS"
echo "# harness $(git -C "$HERE" rev-parse HEAD)$(git -C "$HERE" diff --quiet HEAD -- . ../gpu_compositing ../../../tools || echo " DIRTY")"
echo "# started $(date -u +%FT%TZ)"
echo "# pre-run screenshot local/$(basename "$SHOT")"
echo "# probe sha256 local    $(sha256sum < "$HERE/soak-cards-probe.js" | cut -d' ' -f1)"
} > "$OUT"
"$KSSH" "$T" 'cat > /home/root/kiosk-probe.js' < "$HERE/soak-cards-probe.js" || exit 1
RESTORE_PENDING=1
{ printf '%s\n' "$COG_CACHE_FN"; cat <<'EOF'; } | "$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1
C=/data/config/kiosk.conf
if [ -e $C.wpe-bak ] || [ -e $C.wpe-absent ]; then
	echo "# REFUSED: a kiosk.conf backup exists -- an earlier run did not restore"; exit 3
fi
if [ -f $C ]; then cp -p $C $C.wpe-bak || exit 1; else : > $C.wpe-absent; fi
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_PROBE=1' >> $C
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
echo "# probe sha256 deployed $(sha256sum < /home/root/kiosk-probe.js | cut -d' ' -f1)"
echo "# boot-start $(cat /proc/sys/kernel/random/boot_id)"
clear_cog_cache
systemctl restart kiosk
echo "# start-epoch $(date +%s) $(systemctl show -p NRestarts kiosk)"
echo "# vmstat-start $(grep -E '^(pswpin|pswpout) ' /proc/vmstat | tr '\n' ' ')"
EOF
rc=$?
[ $rc -eq 3 ] && RESTORE_PENDING=0
[ $rc -eq 0 ] || exit 1
START=$(sed -n 's/^# start-epoch \([0-9]*\).*/\1/p' "$OUT")
[ -n "$START" ] || { echo "# START FAILED" >> "$OUT"; exit 1; }

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

echo "# complete $(date -u +%FT%TZ)" >> "$OUT"
