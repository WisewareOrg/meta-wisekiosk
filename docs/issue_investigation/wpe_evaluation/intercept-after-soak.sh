#!/bin/bash
# intercept-after-soak.sh -- orchestrate-tonight.sh (pid 2025325) still has the OLD V1b
# re-enable section baked in after the soak (inode rule: can't edit a running script's own
# future code). Waits for the soak to finish, then kills that process's group BEFORE it reaches
# V1b, verifies kiosk.conf, and launches orchestrate-v1-real.sh in its place.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
TONIGHT_LOG="$LOGDIR/orchestrate-tonight.log"
TONIGHT_PID=2025325
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
KNOWN_GOOD="KIOSK_INSPECTOR=0"

echo "--- waiting for the soak to finish ---"
until grep -q "=== soak exit=" "$TONIGHT_LOG" 2>/dev/null; do sleep 5; done
echo "soak finished, killing orchestrate-tonight before it reaches V1b"

pgid=$(ps -o pgid= -p "$TONIGHT_PID" 2>/dev/null | tr -d ' ')
if [ -n "$pgid" ]; then
	kill -TERM -- -"$pgid"
	sleep 2
fi
if ps -p "$TONIGHT_PID" > /dev/null 2>&1; then
	echo "still alive after TERM, escalating to KILL"
	kill -KILL -- -"$pgid" 2>/dev/null
	sleep 1
fi
echo "orchestrate-tonight gone: $(ps -p "$TONIGHT_PID" > /dev/null 2>&1 && echo STILL_ALIVE || echo CONFIRMED_DEAD)"

CONF=$("$KSSH" "$T" 'cat /data/config/kiosk.conf')
echo "kiosk.conf: $CONF"
if [ "$CONF" != "$KNOWN_GOOD" ]; then
	echo "kiosk.conf NOT known-good -- restoring directly (soak/smoothness leave no override; this would mean an interrupted V1b-prep, unexpected at this point)"
	"$KSSH" "$T" "printf '%s\n' '$KNOWN_GOOD' > /data/config/kiosk.conf"
	"$KSSH" "$T" 'systemctl restart kiosk'
	CONF2=$("$KSSH" "$T" 'cat /data/config/kiosk.conf')
	echo "kiosk.conf after manual restore: $CONF2"
	[ "$CONF2" = "$KNOWN_GOOD" ] || { echo "ABORT: could not get kiosk.conf to known-good"; exit 1; }
fi
echo "KIOSK_CONF_CONFIRMED_KNOWN_GOOD"

BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
rm -f "$LOGDIR/orchestrate-v1-real.log" "$LOGDIR/orchestrate-v1-real.log.done"
setsid bash "$BURST/orchestrate-v1-real.sh" > "$LOGDIR/orchestrate-v1-real.log" 2>&1 < /dev/null &
disown
echo "launched orchestrate-v1-real.sh pid=$!"
echo INTERCEPT_AFTER_SOAK_DONE
