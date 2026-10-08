#!/bin/bash
# check-baseline-stop-journal.sh <ssh-target> <boot-id> -- read-only: every kiosk.service stop
# event in the named boot's persistent journal (exit code, dumped or not).
set -u
T=${1:?ssh-target}; BOOT=${2:?boot-id}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
"$KSSH" "$T" "journalctl -u kiosk --boot=$BOOT --no-pager | grep -iE 'stopping|stopped|main process exited'"
