#!/bin/bash
# check-cards-once-x.sh <ssh-target> -- one-shot X/surf cards read: deploys x-cards-probe.js,
# waits once for a sample, prints exactly what it read, restores script.js+cache+kiosk. Unlike
# poll-cards-live-x.sh this does NOT loop until live -- it is the "exercise it and log what it
# reads" / "check right after" instrument, never run concurrently with p7_min's own script.js
# (this script's own restore removes x-cards-probe.js before returning, so the two are never
# loaded at the same time by construction).
set -u
T=${1:?ssh-target}
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
KSSH=$ROOT/tools/kiosk-ssh.sh

restore_x() {
	"$KSSH" "$T" ': > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk'
}
trap restore_x EXIT
trap 'exit 1' INT TERM HUP

"$KSSH" "$T" 'cat > /home/root/.surf/script.js' < "$HERE/x-cards-probe.js"
"$KSSH" "$T" 'rm -rf /home/root/.surf/cache; systemctl restart kiosk'
sleep 20
LAST=$("$KSSH" "$T" 'export DISPLAY=:0; for id in $(xwininfo -root -children | grep "0x" | awk "{print \$1}"); do xprop -len 64 -id $id WM_NAME 2>/dev/null | grep "CPX|"; done' 2>/dev/null | tail -1)
echo "CARDS_ONCE_X: ${LAST:-<no CPX| title read>}"
