#!/bin/bash
# check-stall-correlation.sh <ssh-target> <out-prefix> -- read-only. For each S3 smoothness
# run's kiosk-restart epoch, pulls 90s of kiosk.service + wisekiosk.service journal
# (short-monotonic) to correlate WPE's early-window stalls with backend fetches or WPE log lines.
set -u
T=${1:?ssh-target}; PFX=${2:?out-prefix}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh

# restart epochs: run-smoothness.sh's "# capture start" UTC timestamps (the systemctl restart
# kiosk moment), one per S3 run.
declare -A STARTS=(
  [1]="2026-10-05T12:45:20Z"
  [2]="2026-10-05T12:55:26Z"
  [3]="2026-10-05T13:05:33Z"
)

for run in 1 2 3; do
  START=${STARTS[$run]}
  # systemd's timestamp parser wants "YYYY-MM-DD HH:MM:SS UTC", not ISO8601 T/Z.
  SINCE_SD=$(date -u -d "$START" '+%Y-%m-%d %H:%M:%S UTC')
  UNTIL_SD=$(date -u -d "$START + 90 seconds" '+%Y-%m-%d %H:%M:%S UTC')
  OUT="${PFX}-run${run}.txt"
  {
    echo "# check-stall-correlation.sh run=$run restart=$START since='$SINCE_SD' until='$UNTIL_SD'"
    "$KSSH" "$T" "grep '^meta-wisekiosk ' /etc/buildinfo; rauc status 2>&1 | grep 'Booted from'"
    echo "=== kiosk.service ==="
    "$KSSH" "$T" "journalctl -u kiosk -o short-monotonic --no-pager --since '$SINCE_SD' --until '$UNTIL_SD'"
    echo "=== wisekiosk.service ==="
    "$KSSH" "$T" "journalctl -u wisekiosk -o short-monotonic --no-pager --since '$SINCE_SD' --until '$UNTIL_SD'"
  } > "$OUT"
done
