#!/bin/bash
# poll-cards-live.sh <ssh-target> -- blocks until cards-probe.js reports c=4 l=4 (every park
# card open with a rendered leaderboard). Deploys cards-probe.js alone under KIOSK_PROBE=1,
# polls the journal's latest CP| sample every 35s. No overall timeout: outside park hours this
# can legitimately run for hours, and the rule is to wait for the next live window, not to
# shorten it -- a heartbeat line every ~30 min makes a long wait visible rather than a silent
# hang. kiosk.conf is backed up and restored (cmp-verified) on every exit, interrupts included.
set -u
T=${1:?ssh-target}
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
KSSH=$ROOT/tools/kiosk-ssh.sh
BACKUP=$(mktemp)
RESTORE_PENDING=0

restore_conf() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$BACKUP"
	"$KSSH" "$T" 'rm -f /home/root/kiosk-probe.js; systemctl restart kiosk'
	AFTER=$(mktemp)
	"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$AFTER"
	cmp "$BACKUP" "$AFTER" && echo "RESTORE_IDENTICAL" || echo "RESTORE_MISMATCH"
	rm -f "$BACKUP" "$AFTER"
}
trap restore_conf EXIT
trap 'exit 1' INT TERM HUP

echo "--- deploying cards-probe.js (KIOSK_PROBE=1) ---"
"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$BACKUP"
RESTORE_PENDING=1
"$KSSH" "$T" 'cat > /home/root/kiosk-probe.js' < "$HERE/cards-probe.js"
DEPLOY_OUT=$("$KSSH" "$T" "sh -s" <<'REMOTE'
C=/data/config/kiosk.conf
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_PROBE=1' >> $C
systemctl restart kiosk
echo "start-epoch $(date +%s)"
REMOTE
)
printf '%s\n' "$DEPLOY_OUT"
START=$(printf '%s\n' "$DEPLOY_OUT" | sed -n 's/^start-epoch \([0-9]*\)$/\1/p')
[ -n "$START" ] || { echo "ABORT: no start-epoch read back"; exit 1; }

echo "--- polling for c=4 l=4 (every 35s, no timeout) ---"
elapsed=0
heartbeat_at=1800
while :; do
	sleep 35
	elapsed=$((elapsed + 35))
	LAST=$("$KSSH" "$T" "journalctl -u kiosk --since @$START -o cat --no-pager | grep 'CP|' | tail -1")
	if [ -z "$LAST" ]; then
		echo "t=${elapsed}s: no CP| sample yet"
	else
		echo "t=${elapsed}s: $LAST"
		C=$(printf '%s\n' "$LAST" | sed -n 's/.*|c=\([0-9]*\)|.*/\1/p')
		L=$(printf '%s\n' "$LAST" | sed -n 's/.*|l=\([0-9]*\)$/\1/p')
		if [ "${C:-0}" = 4 ] && [ "${L:-0}" = 4 ]; then
			echo "LIVE: c=4 l=4 at t=${elapsed}s"
			break
		fi
	fi
	if [ "$elapsed" -ge "$heartbeat_at" ]; then
		echo "heartbeat: still waiting for cards to go live, elapsed ${elapsed}s"
		heartbeat_at=$((heartbeat_at + 1800))
	fi
done

echo CARDS_LIVE
