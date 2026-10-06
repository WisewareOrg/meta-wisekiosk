#!/bin/bash
# poll-cards-live-x.sh <ssh-target> [min-live] -- X/surf variant of poll-cards-live.sh. Deploys
# x-cards-probe.js as /home/root/.surf/script.js (surf's own script-injection point, no
# KIOSK_PROBE env var involved on this image), polls WM_NAME (xwininfo + xprop, the same scan
# run-appliance.sh uses for its own MP|/BL| readback) every ~10s for c=4 l>=min-live. No overall
# timeout -- but aborts if the kiosk service's NRestarts increases (a crash, not a slow page)
# or if two kiosk-drmgrab frames 3s apart hash identical (FROZEN; DRM/KMS scanout read, so it
# works the same under X as under WPE). A heartbeat line every 10 min. Restores script.js
# (empty) and the cache on every exit, interrupts included -- same restore run-appliance.sh
# itself does.
set -u
T=${1:?ssh-target}; MIN_LIVE=${2:-4}
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
KSSH=$ROOT/tools/kiosk-ssh.sh

restore_x() {
	"$KSSH" "$T" ': > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk'
	echo "X_SCRIPT_RESTORED"
}
trap restore_x EXIT
trap 'exit 1' INT TERM HUP

echo "--- deploying x-cards-probe.js ---"
"$KSSH" "$T" 'cat > /home/root/.surf/script.js' < "$HERE/x-cards-probe.js"
"$KSSH" "$T" 'rm -rf /home/root/.surf/cache; systemctl restart kiosk'

BASELINE_RESTARTS=$("$KSSH" "$T" 'systemctl show -p NRestarts kiosk' | cut -d= -f2)
echo "baseline NRestarts=$BASELINE_RESTARTS"

frozen_check() {
	local out
	out=$("$KSSH" "$T" 'sh -s' <<'REMOTE' 2>&1
F=/tmp/poll-cards-x-frozen.$$
kiosk-drmgrab "$F.1.ppm" > /dev/null 2>&1; rc1=$?
sleep 3
kiosk-drmgrab "$F.2.ppm" > /dev/null 2>&1; rc2=$?
if [ $rc1 -eq 0 ] && [ $rc2 -eq 0 ] && [ -s "$F.1.ppm" ] && [ -s "$F.2.ppm" ]; then
	h1=$(md5sum < "$F.1.ppm" | cut -d' ' -f1)
	h2=$(md5sum < "$F.2.ppm" | cut -d' ' -f1)
	[ "$h1" = "$h2" ] && echo FROZEN || echo ADVANCING
else
	echo CANNOT_TELL
fi
rm -f "$F.1.ppm" "$F.2.ppm"
REMOTE
)
	printf '%s\n' "$out" | tail -1
}

echo "--- polling for c=4 l>=$MIN_LIVE (every 10s, no timeout) ---"
elapsed=0
heartbeat_at=600
while :; do
	sleep 10
	elapsed=$((elapsed + 10))

	RESTARTS=$("$KSSH" "$T" 'systemctl show -p NRestarts kiosk' | cut -d= -f2)
	if [ "${RESTARTS:-0}" != "$BASELINE_RESTARTS" ]; then
		echo "ABORT: kiosk NRestarts changed ($BASELINE_RESTARTS -> $RESTARTS) at t=${elapsed}s"
		exit 1
	fi

	LAST=$("$KSSH" "$T" 'export DISPLAY=:0; for id in $(xwininfo -root -children | grep "0x" | awk "{print \$1}"); do xprop -len 64 -id $id WM_NAME 2>/dev/null | grep "CPX|"; done' 2>/dev/null | tail -1)
	if [ -z "$LAST" ]; then
		echo "t=${elapsed}s: no CPX| title yet"
	else
		echo "t=${elapsed}s: $LAST"
		C=$(printf '%s\n' "$LAST" | grep -oE '\|c=[0-9]+' | grep -oE '[0-9]+')
		L=$(printf '%s\n' "$LAST" | grep -oE '\|l=[0-9]+' | grep -oE '[0-9]+')
		if [ "${C:-0}" = 4 ] && [ "${L:-0}" -ge "$MIN_LIVE" ] 2>/dev/null; then
			echo "LIVE: c=4 l=${L} (>=$MIN_LIVE) at t=${elapsed}s"
			break
		fi
	fi

	if [ "$elapsed" -ge "$heartbeat_at" ]; then
		FROZEN=$(frozen_check)
		echo "heartbeat t=${elapsed}s: still waiting for cards to go live, frozen_check=$FROZEN"
		if [ "$FROZEN" = FROZEN ]; then
			echo "ABORT: board reports FROZEN at t=${elapsed}s"
			exit 1
		fi
		heartbeat_at=$((heartbeat_at + 600))
	fi
done

echo CARDS_LIVE_X
