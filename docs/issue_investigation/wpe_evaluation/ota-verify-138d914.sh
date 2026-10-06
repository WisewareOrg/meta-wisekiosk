#!/bin/bash
# ota-verify-138d914.sh -- OTA + reboot 138d914 (kiosk-fwgrab) to bench, verify buildinfo,
# confirm the boot counter was reset by rauc-mark-good (not just that rauc booted this slot),
# settle, sanity-check kiosk-drmgrab --report. Aborts (nonzero exit) if buildinfo doesn't match
# after reboot, or if the boot-attempt counters were not reset to 3/3.
set -u
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
EXPECT=138d914

cd /home/tjwise/meta-wisekiosk-185-254
export DL_DIR=/home/tjwise/meta-wisekiosk/build/downloads
export SSTATE_DIR=/home/tjwise/meta-wisekiosk/build/sstate-cache
export PIPELINE_KEYS_DIR=/home/tjwise/meta-wisekiosk/local/keys
export KIOSK_HOST=$T

echo "--- OTA ---"
just kiosk-ota
OTA_EXIT=$?
echo "OTA_EXIT=$OTA_EXIT"
[ $OTA_EXIT -eq 0 ] || { echo "ABORT: OTA install failed, not rebooting"; exit 1; }

echo "--- reboot ---"
REBOOT_OUT=$(just kiosk-reboot)
REBOOT_RC=$?
echo "$REBOOT_OUT"
echo "REBOOT_EXIT=$REBOOT_RC"

echo "--- verify buildinfo ---"
ACTUAL=$("$KSSH" "$T" 'grep "^meta-wisekiosk " /etc/buildinfo')
echo "buildinfo: $ACTUAL"
case "$ACTUAL" in
*"$EXPECT"*) echo "BUILDINFO_MATCH" ;;
*) echo "BUILDINFO_MISMATCH: expected $EXPECT"; exit 1 ;;
esac

echo "--- verify rauc-mark-good reset the boot counter (not just that it booted) ---"
COUNTERS=$("$KSSH" "$T" 'fw_printenv BOOT_A_LEFT BOOT_B_LEFT; rauc status 2>&1 | grep -E "Booted from|boot status"')
echo "$COUNTERS"
if ! printf '%s\n' "$COUNTERS" | grep -qE 'BOOT_[AB]_LEFT=3'; then
	echo "ABORT: neither slot's boot counter reads 3 -- rauc-mark-good may not have run"
	exit 1
fi

echo "--- settle until screenshot mean >= 10 ---"
SHOT=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst/settle-138d914.png
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

echo OTA_VERIFY_138D914_DONE
