#!/bin/bash
# sanity-fwgrab.sh <ssh-target> -- one-shot sanity pass before the fw burst: /dev/vchiq
# permissions, one kiosk-fwgrab capture (rc, stderr, dims, mean via identify), one
# kiosk-drmgrab --report capture straight after for comparison. Exits nonzero (and the
# caller stops the chain there) if fwgrab fails.
set -u
T=${1:?ssh-target}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh

echo "--- /dev/vchiq ---"
"$KSSH" "$T" 'ls -l /dev/vchiq'

echo "--- kiosk-fwgrab ---"
"$KSSH" "$T" 'sh -s' <<'REMOTE'
rm -f /tmp/sanity-fw.ppm
err=$(kiosk-fwgrab /tmp/sanity-fw.ppm 2>&1)
rc=$?
echo "rc=$rc"
[ -n "$err" ] && printf 'stderr: %s\n' "$err"
if [ -f /tmp/sanity-fw.ppm ]; then
    identify -format 'dims=%wx%h mean=%[fx:mean*255]\n' /tmp/sanity-fw.ppm
else
    echo "no output file"
fi
rm -f /tmp/sanity-fw.ppm
exit $rc
REMOTE
FWGRAB_RC=$?
if [ $FWGRAB_RC -ne 0 ]; then
	echo "ABORT: kiosk-fwgrab failed rc=$FWGRAB_RC"
	exit 1
fi

echo "--- kiosk-drmgrab --report (comparison, right after) ---"
"$KSSH" "$T" 'sh -s' <<'REMOTE'
rm -f /tmp/sanity-drm.ppm
err=$(kiosk-drmgrab --report /tmp/sanity-drm.ppm 2>&1)
rc=$?
echo "rc=$rc"
[ -n "$err" ] && printf 'stderr: %s\n' "$err"
if [ -f /tmp/sanity-drm.ppm ]; then
    identify -format 'dims=%wx%h mean=%[fx:mean*255]\n' /tmp/sanity-drm.ppm
else
    echo "no output file"
fi
rm -f /tmp/sanity-drm.ppm
REMOTE

echo SANITY_FWGRAB_DONE
