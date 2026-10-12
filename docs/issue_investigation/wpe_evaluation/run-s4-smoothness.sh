#!/bin/bash
# run-s4-smoothness.sh <ssh-target> <role> <out> [min-live]
#
# run-smoothness.sh, for S4, with the cards-live gate added: the probe is the composite
# smoothness-cards-probe.js (p7_min.js + cards-probe.js, bytes unchanged in each half), so the
# capture carries both the MP| frame-time payload and CP| cards-live samples. After capture, EVERY
# CP| sample in the window must read l >= min-live (default 4, parse_cards_probe.all_at_least)
# or the whole run is VOID, exit 4 -- a run where a park's leaderboard drops out partway through
# is not a valid smoothness measurement, averaging it away would hide exactly the failure this
# gate exists to catch. min-live below 4 is a deliberate relaxation for a window where a park is
# known closed (one card legitimately never shows l's 4th count) -- it still VOIDs a run where
# live count drops BELOW that floor mid-capture, so a second failure is still caught.
#
# One smoothness capture under cog, the sequence of ../gpu_compositing/run-appliance.sh with the
# WPE readback:
#   pre-run  screenshot into local/ for the card state, retried every 10 s until it is not blank
#            and its mean luma (0-255) is at least 10, the rendered dashboard; short of that at
#            120 s is VOID, exit 3, before anything is deployed; so is cog's cache dir absent or
#            empty (cog-cache.sh's require_cog_cache)
#   deploy   the composite probe to /home/root/kiosk-probe.js; kiosk.conf backed up, KIOSK_PROBE=1
#            appended
#   capture  cog's cache cleared; systemctl restart kiosk; sleep 585; the kiosk journal's MP| and
#            CP| lines since the restart (cog prints each title as "TITLE <title>", CP| reaches
#            stdout via --enable-write-console-messages-to-stdout, bundled with KIOSK_PROBE=1),
#            loadavg, MemAvailable
#   restore  kiosk.conf from its backup, probe removed, cog's cache cleared, kiosk restarted
# cog's cache: cog-cache.sh; each clear records "cleared <dir> (<n> entries)" or "no cache dir
# found".
# Around it: the R1 header run-appliance.sh records, the active CRTC mode read from DRM debugfs
# before deploy and after readback (anything but 1280x720 on either read is VOID, exit 3), the
# served bundle name from cog's cache, and kiosk NRestarts. A kiosk.conf backup already on the
# board means an earlier run did not restore; the run refuses, exit 1, and leaves it alone.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; OUT=${3:?out}; MIN_LIVE=${4:-4}
SLEEP=585
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
KSSH=$ROOT/tools/kiosk-ssh.sh
PROBE=$HERE/smoothness-cards-probe.js
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

mode() { "$KSSH" "$T" 'grep "mode:" /sys/kernel/debug/dri/0/state' 2>&1; }
live720() { printf '%s\n' "$1" | grep -c 'mode: "1280x720"'; }

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
echo "# run-s4-smoothness.sh role=$ROLE probe=$(basename "$PROBE") sleep=$SLEEP"
echo "# harness $(git -C "$HERE" rev-parse HEAD)$(git -C "$HERE" diff --quiet HEAD -- . ../gpu_compositing ../../../tools || echo " DIRTY")"
echo "# started $(date -u +%FT%TZ)"
echo "# pre-run screenshot local/$(basename "$SHOT")"
echo "# probe sha256 local    $(sha256sum < "$PROBE" | cut -d' ' -f1)"
"$KSSH" "$T" 'sh -s' <<'PRE'
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
echo "# config.json sha256 $(sha256sum /data/config/config.json | cut -d' ' -f1)"
sed 's/^\(KIOSK_URL=\).*/\1<masked>/; s/^/# kiosk.conf /' /data/config/kiosk.conf
PRE
"$KSSH" "$T" 'cat /data/config/config.json' | python3 -c 'import json,sys; c=json.load(sys.stdin); m=[x for x in c["modules"] if x["module"]=="park_wait_times"]; print("# park_wait_times.rotation_interval_seconds", m[0].get("options",{}).get("rotation_interval_seconds","ABSENT (schema default)") if m else "NO park_wait_times MODULE")'
} > "$OUT"

M0=$(mode); printf '%s\n' "$M0" | sed 's/^/# mode-before /' >> "$OUT"

"$KSSH" "$T" 'cat > /home/root/kiosk-probe.js' < "$PROBE" || { echo "# DEPLOY FAILED" >> "$OUT"; exit 1; }
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
[ $rc -eq 0 ] || exit 1

{
echo "# capture start $(date -u +%FT%TZ)"
"$KSSH" "$T" 'sh -s' 2>&1 <<EOF
$COG_CACHE_FN
clear_cog_cache
systemctl restart kiosk
S=\$(date +%s)
echo "restarted, sleeping $SLEEP"
sleep $SLEEP
echo "=== journal MP| ==="
journalctl -u kiosk --since @\$S -o cat --no-pager | grep 'MP|'
echo "=== journal CP| ==="
journalctl -u kiosk --since @\$S -o cat --no-pager | grep 'CP|'
echo "LOAD \$(cat /proc/loadavg)"
echo "MEM \$(grep MemAvailable /proc/meminfo)"
echo "=== DONE ==="
EOF
echo "# capture end $(date -u +%FT%TZ)"
} >> "$OUT"

M1=$(mode); printf '%s\n' "$M1" | sed 's/^/# mode-after /' >> "$OUT"
{ printf '%s\n' "$COG_CACHE_FN"; cat <<'POST'; } | "$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1
echo "# bundle $(grep -rhoE 'index-[A-Za-z0-9_]+\.js' "$(cog_cache_dir)" | sort -u | tr '\n' ' ')"
echo "# kiosk $(systemctl show -p NRestarts -p ActiveEnterTimestamp kiosk | tr '\n' ' ')"
POST
restore_conf

n=$(grep -c 'MP|' "$OUT")
if [ "$(live720 "$M0")" -ne 1 ] || [ "$(live720 "$M1")" -ne 1 ]; then
	echo "# VOID: 1280x720 not live before and after" >> "$OUT"; echo "VOID (display mode) -- $OUT"; exit 3
fi
[ "$n" -ge 1 ] || { echo "# NO PAYLOAD: no MP| line read back" >> "$OUT"; echo "no payload -- $OUT"; exit 1; }

CP_LINES=$(grep 'CP|' "$OUT")
if [ -z "$CP_LINES" ]; then
	echo "# VOID: no CP| line read back -- cards-live state unknown" >> "$OUT"
	echo "VOID (no cards-probe payload) -- $OUT"; exit 4
fi
# The gate is judged only inside p7_min's own measured window (t >= STEADY_FROM, the same
# warm-up it excludes from its stall-rate numbers): cards-probe.js samples once right at the
# load event, before the framework has painted any card, and that sample legitimately reads
# l=0 -- not a card dropping, and not evidence this capture's actual window saw anything.
STEADY_FROM=15.0
JUDGE_RESULT=$(printf '%s\n' "$CP_LINES" | python3 -c '
import sys, re
sys.path.insert(0, "'"$HERE"'")
import parse_cards_probe as pcp
PAT = re.compile(r"CP\|t=(\d+)\|c=(\d+)\|l=(\d+)")
lines = sys.stdin.read().splitlines()
excluded = [l for l in lines if (m := PAT.search(l)) and int(m.group(1)) < '"$STEADY_FROM"']
judged = [l for l in lines if (m := PAT.search(l)) and int(m.group(1)) >= '"$STEADY_FROM"']
print("EXCLUDED:" + ("; ".join(excluded) if excluded else "none"))
if not judged:
	print("VOID: no CP| samples inside the measured window")
	sys.exit(1)
try:
	live = pcp.all_at_least(judged, '"$MIN_LIVE"')
except ValueError as e:
	print(f"VOID: {e}")
	sys.exit(1)
print(f"JUDGED: {len(judged)} samples")
sys.exit(0 if live else 1)
')
JUDGE_RC=$?
printf '%s\n' "$JUDGE_RESULT" | sed 's/^/# /' >> "$OUT"
if [ $JUDGE_RC -ne 0 ]; then
	echo "# VOID: cards dropped below l=$MIN_LIVE at some point inside the measured window (t>=${STEADY_FROM}s)" >> "$OUT"
	echo "VOID (cards not live throughout the measured window) -- $OUT"; exit 4
fi
echo "# cards-live: l>=$MIN_LIVE throughout the measured window (t>=${STEADY_FROM}s)" >> "$OUT"

echo "# complete $(date -u +%FT%TZ): $n payload line(s)" >> "$OUT"
echo "captured -> $OUT"
