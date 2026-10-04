#!/bin/sh
# time-to-page-x.sh [READ_AT] -- runs ON the board, X baseline image only.
#
# Reads the "T <epoch_ms>" title that time-to-page.js (deployed as surf's script.js) sets when the
# page is up, at uptime READ_AT (default 115) with no polling before it, and prints time to page:
# epoch_ms - boot_epoch_ms. boot_epoch_ms is read at a wall-clock second boundary, because
# busybox date has no %N: spin until `date +%s` rolls over, then read /proc/uptime. A clock
# step or timesyncd sync logged after kiosk.service started puts the two readings in different
# wall-clock frames, so that boot is printed SUSPECT.
READ_AT=${1:-115}
export DISPLAY=:0

NOW=$(cut -d. -f1 /proc/uptime)
[ "$NOW" -lt "$READ_AT" ] && sleep $((READ_AT - NOW))

# xwininfo -tree, not -children: surf is override-redirect.
TITLE=''
for _ in 1 2 3 4 5; do
	for id in $(xwininfo -root -tree 2>/dev/null | awk '/^ +0x/ { print $1 }'); do
		t=$(xprop -id "$id" WM_NAME 2>/dev/null | sed 's/^WM_NAME([A-Z_]*) = "//; s/"$//')
		case "$t" in 'T '[0-9]*) case "${t#T }" in *[!0-9]*) ;; *) TITLE=$t ;; esac ;; esac
	done
	[ -n "$TITLE" ] && break
	sleep 10
done

S=$(date +%s)
while [ "$(date +%s)" = "$S" ]; do :; done
UP=$(cut -d' ' -f1 /proc/uptime)

echo "boot_id:       $(cat /proc/sys/kernel/random/boot_id)"
echo "read_at_s:     ${UP%.*}"
if [ -z "$TITLE" ]; then
	echo 'RESULT: TIMEOUT -- no "T <epoch_ms>" title found'
	exit 1
fi
echo "title:         $TITLE"
KSTART=$(systemctl show -p ExecMainStartTimestampMonotonic --value kiosk)
STEPS=$(journalctl -b -o short-monotonic --no-pager |
	grep -E 'Initial clock synchronization|Time has been changed|Contacted time server' |
	awk -v k="$KSTART" '{ m = $0; sub(/^\[ */, "", m); sub(/\].*/, "", m); if (m * 1000000 > k) print }')
if [ -n "$STEPS" ]; then
	printf '%s\n' "$STEPS" | sed 's/^/clock_step:    /'
	echo "SUSPECT: the wall clock changed after kiosk.service started"
fi
awk -v e="${TITLE#T }" -v s="$S" -v up="$UP" 'BEGIN {
	boot = (s + 1) * 1000 - up * 1000
	printf "boot_epoch_ms: %.0f\n", boot
	printf "RESULT_time_to_page_s: %.2f\n", (e - boot) / 1000
}'
