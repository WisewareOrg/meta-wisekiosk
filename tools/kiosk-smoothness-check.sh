#!/bin/bash
# kiosk-smoothness-check.sh <ssh-target> [min-live]
#
# One smoothness capture under wpe-kiosk, judged against the X baseline by
# kiosk-perf-verdict.py. The probe is the composite smoothness-cards-probe.js
# (p7_min.js + cards-probe.js), so the capture carries both the MP| frame-time payload
# and CP| cards-live samples; every CP| sample at t >= 15 s must read l >= min-live
# (default 4). min-live below 4 is a deliberate relaxation for a window where a park is
# known closed.
#
#   pre-run  screenshot, retried every 10 s until it is not blank and its mean luma
#            (0-255) is at least 10, the rendered dashboard; short of that at 120 s is
#            could-not-tell before anything is deployed; so is wpe-kiosk's WebKit cache
#            dir absent or empty (kiosk-cache.sh's require_kiosk_cache)
#   deploy   the composite probe to /home/root/kiosk-probe.js; kiosk.conf backed up,
#            KIOSK_PROBE=1 appended
#   capture  the cache cleared; systemctl restart kiosk; sleep 585; the kiosk journal's
#            MP| and CP| lines since the restart (wpe-kiosk prints each title as
#            "TITLE <title>", and CP| reaches stdout through WPE_KIOSK_CONSOLE, both
#            under KIOSK_PROBE=1), loadavg, MemAvailable
#   restore  kiosk.conf from its backup, probe removed, the cache cleared, kiosk
#            restarted
# Each cache clear records "cleared <dir> (<n> entries)" or "no cache dir found".
# Around it: the R1 header, the active CRTC mode read from DRM debugfs before deploy and
# after readback, the served bundle name from the cache, and kiosk NRestarts after the
# restart and at the end. A kiosk.conf backup already on the board means an earlier run
# did not restore; the run refuses and leaves it alone.
#
# Everything is written to stdout. Exit: kiosk-perf-verdict.py's 0 (no regression),
# 1 (regression) or 2 (could not tell); also 2 on no rendered dashboard, an absent or
# empty cache, a kiosk.conf backup already present, a failed deploy, 1280x720 not live
# before and after, an NRestarts change during the capture, or a misinvocation.
set -u
T=${1:-}; MIN_LIVE=${2:-4}
[ -n "$T" ] || { echo "usage: kiosk-smoothness-check.sh <ssh-target> [min-live]" >&2; exit 2; }
[[ $MIN_LIVE =~ ^[0-9]+$ ]] || { echo "min-live '$MIN_LIVE' is not a count" >&2; exit 2; }
SLEEP=585
HERE=$(dirname "$(readlink -f "$0")")
KSSH=$HERE/kiosk-ssh.sh
PROBE=$HERE/smoothness-cards-probe.js
# shellcheck source=kiosk-cache.sh
. "$HERE/kiosk-cache.sh"
WORK=$(mktemp -d) || { echo "could not tell: no local work directory" >&2; exit 2; }
OUT=$WORK/capture.txt
SHOT=$WORK/pre-run.png
: > "$OUT"

# kiosk.conf is restored on any exit once this run has backed it up, interrupts included;
# the capture is then printed and the work directory removed.
RESTORE_PENDING=0
restore_conf() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	{ printf '%s\n' "$KIOSK_CACHE_FN"; cat <<'RESTORE'; } | "$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1
C=/data/config/kiosk.conf
if [ -f $C.wpe-bak ]; then mv $C.wpe-bak $C; elif [ -e $C.wpe-absent ]; then rm -f $C $C.wpe-absent; else echo "# NO BACKUP -- kiosk.conf left as found"; fi
rm -f /home/root/kiosk-probe.js
clear_kiosk_cache
systemctl restart kiosk
n=$(grep -c '^KIOSK_PROBE' $C 2>/dev/null)
echo "# restored: kiosk.conf KIOSK_PROBE lines ${n:-none, file absent}, kiosk restarted"
RESTORE
}
# shellcheck disable=SC2317  # runs from the EXIT trap
finish() {
	restore_conf
	cat "$OUT"
	rm -rf "$WORK"
}
trap finish EXIT
trap 'exit 2' INT TERM HUP

mode() { "$KSSH" "$T" 'grep "mode:" /sys/kernel/debug/dri/0/state' 2>&1; }
live720() { printf '%s\n' "$1" | grep -c 'mode: "1280x720"'; }

for wait in 0 10 20 30 40 50 60 70 80 90 100 110 120; do
	[ "$wait" -gt 0 ] && { rm -f "$SHOT"; sleep 10; }
	shot=$("$HERE/kiosk-screenshot.sh" "$T" "$SHOT")
	rc=$?
	printf '%s\n' "$shot"
	mean=$(printf '%s\n' "$shot" | sed -n 's/^min=.* mean=\([0-9.]*\)$/\1/p')
	[ $rc -eq 0 ] && awk -v m="${mean:-0}" 'BEGIN { exit !(m >= 10) }' && break
	[ "$wait" -eq 120 ] && { echo "could not tell: pre-run screenshot not a rendered dashboard after 120 s (last mean ${mean:-none}, rc $rc)" >&2; exit 2; }
done

require_kiosk_cache "$KSSH" "$T"

{
echo "# kiosk-smoothness-check.sh probe=$(basename "$PROBE") sleep=$SLEEP min-live=$MIN_LIVE"
echo "# harness $(git -C "$HERE" rev-parse HEAD)$(git -C "$HERE" diff --quiet HEAD -- . || echo " DIRTY")"
echo "# started $(date -u +%FT%TZ)"
echo "# probe sha256 local    $(sha256sum < "$PROBE" | cut -d' ' -f1)"
"$KSSH" "$T" 'sh -s' <<'PRE'
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
echo "# config.json sha256 $(sha256sum /data/config/config.json | cut -d' ' -f1)"
sed 's/^\(KIOSK_URL=\).*/\1<masked>/; s/^/# kiosk.conf /' /data/config/kiosk.conf
PRE
"$KSSH" "$T" 'cat /data/config/config.json' | python3 -c 'import json,sys; c=json.load(sys.stdin); m=[x for x in c["modules"] if x["module"]=="park_wait_times"]; print("# park_wait_times.rotation_interval_seconds", m[0].get("options",{}).get("rotation_interval_seconds","ABSENT (schema default)") if m else "NO park_wait_times MODULE")'
} >> "$OUT"

M0=$(mode); printf '%s\n' "$M0" | sed 's/^/# mode-before /' >> "$OUT"

"$KSSH" "$T" 'cat > /home/root/kiosk-probe.js' < "$PROBE" || { echo "# DEPLOY FAILED" >> "$OUT"; exit 2; }
RESTORE_PENDING=1
"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<'DEPLOY'
C=/data/config/kiosk.conf
if [ -e $C.wpe-bak ] || [ -e $C.wpe-absent ]; then
	echo "# REFUSED: a kiosk.conf backup exists -- an earlier run did not restore"; exit 3
fi
if [ -f $C ]; then cp -p $C $C.wpe-bak || exit 1; else : > $C.wpe-absent; fi
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_PROBE=1' >> $C
echo "# probe sha256 deployed $(sha256sum < /home/root/kiosk-probe.js | cut -d' ' -f1)"
DEPLOY
rc=$?
[ $rc -eq 3 ] && RESTORE_PENDING=0
[ $rc -eq 0 ] || exit 2

{
echo "# capture start $(date -u +%FT%TZ)"
"$KSSH" "$T" 'sh -s' 2>&1 <<EOF
$KIOSK_CACHE_FN
clear_kiosk_cache
systemctl restart kiosk
S=\$(date +%s)
echo "# nrestarts-start \$(systemctl show -p NRestarts --value kiosk)"
echo "restarted, sleeping $SLEEP"
sleep $SLEEP
echo "=== journal MP| ==="
journalctl -u kiosk --since @\$S -o cat --no-pager | grep 'MP|'
echo "=== journal CP| ==="
journalctl -u kiosk --since @\$S -o cat --no-pager | grep 'CP|'
echo "LOAD \$(cat /proc/loadavg)"
echo "MEM \$(grep MemAvailable /proc/meminfo)"
echo "# nrestarts-end \$(systemctl show -p NRestarts --value kiosk)"
echo "=== DONE ==="
EOF
echo "# capture end $(date -u +%FT%TZ)"
} >> "$OUT"

M1=$(mode); printf '%s\n' "$M1" | sed 's/^/# mode-after /' >> "$OUT"
{ printf '%s\n' "$KIOSK_CACHE_FN"; cat <<'POST'; } | "$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1
echo "# bundle $(grep -rhoE 'index-[A-Za-z0-9_]+\.js' "$(kiosk_cache_dir)" | sort -u | tr '\n' ' ')"
echo "# kiosk $(systemctl show -p NRestarts -p ActiveEnterTimestamp kiosk | tr '\n' ' ')"
POST
restore_conf

if [ "$(live720 "$M0")" -ne 1 ] || [ "$(live720 "$M1")" -ne 1 ]; then
	echo "# could not tell: 1280x720 not live before and after" >> "$OUT"; exit 2
fi
r0=$(sed -n 's/^# nrestarts-start \([0-9]*\)$/\1/p' "$OUT")
r1=$(sed -n 's/^# nrestarts-end \([0-9]*\)$/\1/p' "$OUT")
if [ -z "$r0" ] || [ "$r0" != "$r1" ]; then
	echo "# could not tell: kiosk NRestarts ${r0:-unread} -> ${r1:-unread} during the capture" >> "$OUT"; exit 2
fi

python3 "$HERE/kiosk-perf-verdict.py" "$OUT" "$HERE/kiosk-perf-baseline.json" "$MIN_LIVE" > "$WORK/verdict.txt" 2>&1
rc=$?
{ echo "=== kiosk-perf-verdict.py ==="; cat "$WORK/verdict.txt"; } >> "$OUT"
exit $rc
