#!/bin/sh
# Time to page under cog: from boot until the page is up.
#
#   measure-page.sh [READ_AT]    default READ_AT 115 (seconds of uptime)
#
# The boot measured must run time-to-page.js as the page's user script --
# KIOSK_PROBE=1 and KIOSK_PROBE_SCRIPT=/usr/share/kiosk-bootprof/time-to-page.js
# in /data/config/kiosk.conf. Once the present weather glyph has rendered in
# the icon face it titles the page "T <epoch_ms>", and cog writes each title to
# the journal as "TITLE <title>".
#
#   time_to_page = epoch_ms - boot_epoch_ms
#
# boot_epoch_ms is read at a wall-clock second boundary, because busybox date
# has no %N: spin until `date +%s` rolls over, then read /proc/uptime. A clock
# step or timesyncd sync logged after the beacon fired (monotonic stamp later
# than the time to page) puts the two readings in different wall-clock frames,
# so that boot is printed SUSPECT.
#
# Nothing is read before READ_AT: on one saturated core, polling during
# startup inflates the number it is reading.

READ_AT=${1:-115}

NOW=$(cut -d. -f1 /proc/uptime)
[ "$NOW" -lt "$READ_AT" ] && sleep $((READ_AT - NOW))

TITLE=''
for _ in 1 2 3 4 5; do
	TITLE=$(journalctl -b -u kiosk -o cat --no-pager | sed -n 's/^TITLE \(T [0-9][0-9]*\)$/\1/p' | tail -n 1)
	[ -n "$TITLE" ] && break
	sleep 10
done

S=$(date +%s)
while [ "$(date +%s)" = "$S" ]; do :; done
UP=$(cut -d' ' -f1 /proc/uptime)

echo "boot_id:       $(cat /proc/sys/kernel/random/boot_id)"
echo "read_at_s:     ${UP%.*}"
if [ -z "$TITLE" ]; then
	echo "RESULT: TIMEOUT -- no 'TITLE T <epoch_ms>' line in this boot's kiosk journal"
	exit 1
fi
echo "title:         $TITLE"
BOOT=$(awk -v s="$S" -v up="$UP" 'BEGIN { printf "%.0f", (s + 1) * 1000 - up * 1000 }')
TTP=$(awk -v e="${TITLE#T }" -v b="$BOOT" 'BEGIN { printf "%.2f", (e - b) / 1000 }')
STEPS=$(journalctl -b -o short-monotonic --no-pager |
	grep -E 'Initial clock synchronization|Time has been changed|Contacted time server' |
	awk -v t="$TTP" '{ m = $0; sub(/^\[ */, "", m); sub(/\].*/, "", m); if (m + 0 > t + 0) print }')
if [ -n "$STEPS" ]; then
	printf '%s\n' "$STEPS" | sed 's/^/clock_step:    /'
	echo "SUSPECT: the wall clock changed after the beacon fired"
fi
echo "boot_epoch_ms: $BOOT"
echo "RESULT_time_to_page_s: $TTP"
