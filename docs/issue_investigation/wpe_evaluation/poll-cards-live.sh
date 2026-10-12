#!/bin/bash
# poll-cards-live.sh <ssh-target> [min-live] -- blocks until cards-probe.js reports
# c=4 l>=min-live (default 4: every park card open with a rendered leaderboard; pass 3 to
# accept one card legitimately closed for the night). Deploys cards-probe.js alone under
# KIOSK_PROBE=1, polls the journal's latest CP| sample every 35s. No overall timeout: outside
# park hours this can legitimately run for hours, and the rule is to wait for the next live
# window, not to shorten it -- but it aborts (rather than waiting forever on a genuinely bad
# board) if the kiosk service's NRestarts increases after the probe-deploy restart (a crash,
# not a slow page) or if two kiosk-drmgrab frames 3s apart hash identical (FROZEN -- the same
# two-frame check kiosk-render-check.sh uses, done directly here so a frequent poll doesn't
# also pay for that tool's own 30-capture STALE series). A heartbeat line every 10 min makes a
# long wait visible rather than a silent hang. kiosk.conf is backed up and restored
# (cmp-verified) on every exit, interrupts included.
set -u
T=${1:?ssh-target}; MIN_LIVE=${2:-4}
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

BASELINE_RESTARTS=$("$KSSH" "$T" 'systemctl show -p NRestarts kiosk' | cut -d= -f2)
echo "baseline NRestarts=$BASELINE_RESTARTS"

frozen_check() {
	# Two kiosk-drmgrab frames 3s apart, hashed. True (frozen) only if both captures
	# succeeded -- a failed capture must never read as "frozen".
	local out
	out=$("$KSSH" "$T" 'sh -s' <<'REMOTE' 2>&1
F=/tmp/poll-cards-frozen.$$
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

echo "--- polling for c=4 l>=$MIN_LIVE (every 35s, no timeout) ---"
elapsed=0
heartbeat_at=600
while :; do
	sleep 35
	elapsed=$((elapsed + 35))

	RESTARTS=$("$KSSH" "$T" 'systemctl show -p NRestarts kiosk' | cut -d= -f2)
	if [ "${RESTARTS:-0}" != "$BASELINE_RESTARTS" ]; then
		echo "ABORT: kiosk NRestarts changed ($BASELINE_RESTARTS -> $RESTARTS) at t=${elapsed}s"
		exit 1
	fi

	LAST=$("$KSSH" "$T" "journalctl -u kiosk --since @$START -o cat --no-pager | grep 'CP|' | tail -1")
	if [ -z "$LAST" ]; then
		echo "t=${elapsed}s: no CP| sample yet"
	else
		echo "t=${elapsed}s: $LAST"
		C=$(printf '%s\n' "$LAST" | sed -n 's/.*|c=\([0-9]*\)|.*/\1/p')
		L=$(printf '%s\n' "$LAST" | sed -n 's/.*|l=\([0-9]*\)$/\1/p')
		if [ "${C:-0}" = 4 ] && [ "${L:-0}" -ge "$MIN_LIVE" ]; then
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

echo CARDS_LIVE
