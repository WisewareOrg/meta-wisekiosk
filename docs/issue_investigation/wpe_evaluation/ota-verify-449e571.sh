#!/bin/bash
# ota-verify-449e571.sh -- OTA + reboot 449e571 to bench, verify buildinfo, settle, sanity-check
# kiosk-drmgrab --report. Aborts (nonzero exit) if buildinfo doesn't match after reboot.
set -u
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
EXPECT=449e571

cd /home/tjwise/meta-wisekiosk-185
export DL_DIR=/home/tjwise/meta-wisekiosk/build/downloads
export SSTATE_DIR=/home/tjwise/meta-wisekiosk/build/sstate-cache
export PIPELINE_KEYS_DIR=/home/tjwise/meta-wisekiosk/local/keys
export KIOSK_HOST=$T

echo "--- OTA ---"
just kiosk-ota
echo "OTA_EXIT=$?"

echo "--- reboot ---"
just kiosk-reboot
echo "REBOOT_EXIT=$?"

echo "--- verify buildinfo ---"
ACTUAL=$("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')
echo "buildinfo: $ACTUAL"
case "$ACTUAL" in
*"$EXPECT"*) echo "BUILDINFO_MATCH" ;;
*) echo "BUILDINFO_MISMATCH: expected $EXPECT"; exit 1 ;;
esac

"$KSSH" "$T" 'rauc status 2>&1 | grep -E "Booted from|boot status"'

echo "--- settle until screenshot mean >= 10 ---"
SHOT=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst/settle-449e571.png
RC=1
for wait in 0 10 20 30 40 50 60 70 80 90 100 110 120; do
	[ "$wait" -gt 0 ] && { rm -f "$SHOT"; sleep 10; }
	shot=$(/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-screenshot.sh "$T" "$SHOT")
	rc=$?
	printf '%s\n' "$shot"
	mean=$(printf '%s\n' "$shot" | sed -n 's/^min=.* mean=\([0-9.]*\)$/\1/p')
	if [ $rc -eq 0 ] && awk -v m="${mean:-0}" 'BEGIN { exit !(m >= 10) }'; then
		RC=0
		echo "settled after ${wait}s, mean=$mean"
		break
	fi
	rm -f "$SHOT"
done
echo "settle rc=$RC"
[ $RC -eq 0 ] || { echo "ABORT: page did not settle"; exit 1; }

echo "--- sanity: kiosk-drmgrab --report once ---"
"$KSSH" "$T" 'kiosk-drmgrab --report /tmp/sanity.ppm; echo rc=$?; rm -f /tmp/sanity.ppm'

echo OTA_VERIFY_449E571_DONE
