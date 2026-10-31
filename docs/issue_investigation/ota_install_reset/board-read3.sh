#!/bin/bash
# Read-only: last journal lines of recent boots, to bound reset->kernel-start time on clean reboots.
host="root@$1"
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o LogLevel=ERROR)
# shellcheck disable=SC2016
remote='
journalctl --list-boots --no-pager | tail -n 18
for b in -16 -15 -14 -13 -12 -11 -10 -9 -8 -7 -6 -5 -4 -3 -2; do echo "== b=$b"; journalctl -b $b -o short-iso-precise --no-pager | tail -n 2; done
'
"${ssh[@]}" "$host" "$remote"
