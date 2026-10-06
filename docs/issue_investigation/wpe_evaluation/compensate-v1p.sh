#!/bin/bash
# compensate-v1p.sh -- orchestrate-d97d6fe-v4.sh (pid 1894760) is running the pre-fix V1' phase
# (its own inode was already open when the trap fix landed, same rule as run_series/compensate-
# v3): if its subshell dies between editing kiosk.conf and the bottom-of-block restore, the
# device is left with KIOSK_COG_FEATURES=UseDamagingInformationForCompositing set. Waits for it
# to exit, then checks kiosk.conf; if the leftover line is still there, restores from
# kiosk.conf.v1p-orig (the pre-edit snapshot, written unconditionally before the trap-dependent
# part) and cmp-verifies. Self .done in an EXIT trap.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
trap 'touch "$LOGDIR/compensate-v1p.log.done"' EXIT
T=${BENCH:?ssh target, e.g. root@<bench>}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
EVIDENCE=/home/tjwise/185-evidence/render-check-validation
V1P_BACKUP="$EVIDENCE/kiosk.conf.v1p-orig"
D97D6FE_V4_PID=1894760

echo "--- waiting for orchestrate-d97d6fe-v4 (pid $D97D6FE_V4_PID) to exit ---"
while kill -0 "$D97D6FE_V4_PID" 2>/dev/null; do sleep 10; done
echo "d97d6fe-v4 chain exited"

CURRENT=$("$KSSH" "$T" 'cat /data/config/kiosk.conf')
echo "current kiosk.conf: $CURRENT"
if ! printf '%s\n' "$CURRENT" | grep -q 'KIOSK_COG_FEATURES=UseDamagingInformationForCompositing'; then
	echo "KIOSK_CONF_CLEAN -- no compensation needed"
	exit 0
fi
echo "kiosk.conf still carries the V1' override -- the trap-dependent restore did not run"

if [ ! -s "$V1P_BACKUP" ]; then
	echo "ABORT: no $V1P_BACKUP to restore from"
	exit 1
fi
echo "restoring from $V1P_BACKUP"
"$KSSH" "$T" 'cat > /data/config/kiosk.conf' < "$V1P_BACKUP"
"$KSSH" "$T" 'systemctl restart kiosk'
AFTER="${V1P_BACKUP}.compensate-after"
"$KSSH" "$T" 'cat /data/config/kiosk.conf' > "$AFTER"
cmp "$V1P_BACKUP" "$AFTER" && echo "COMPENSATE_V1P_RESTORE_IDENTICAL" || echo "COMPENSATE_V1P_RESTORE_MISMATCH"

echo COMPENSATE_V1P_DONE
