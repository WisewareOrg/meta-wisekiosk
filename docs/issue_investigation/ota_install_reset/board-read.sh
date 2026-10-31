#!/bin/bash
# Read-only post-reset board state for the #245 run-14 reset. Bench only, under the bench lock.
host="root@$1"
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o LogLevel=ERROR)
# shellcheck disable=SC2016
remote='
echo "== dev clock + uptime"; date +%s.%N; cat /proc/uptime; date -Iseconds
echo "== bootstatus"; for f in identity bootstatus timeout timeleft state status nowayout; do printf "%s=" $f; cat /sys/class/watchdog/watchdog0/$f 2>&1; done
echo "== pstore"; ls -la /sys/fs/pstore/; mount | grep pstore
echo "== uv"; for d in /sys/class/hwmon/hwmon*; do echo "$d $(cat $d/name 2>/dev/null) $(cat $d/in0_lcrit_alarm 2>/dev/null)"; done
echo "== list-boots"; journalctl --list-boots --no-pager | tail -6
echo "== prev boot tail"; journalctl -b -1 -o short-iso-precise --no-pager | tail -40
echo "== prev boot kernel tail"; journalctl -b -1 -k -o short-iso-precise --no-pager | tail -10
echo "== cur boot head"; journalctl -b 0 -o short-iso-precise --no-pager | head -5
echo "== cur boot grep"; journalctl -b 0 -k -o short-iso-precise --no-pager | grep -i -E "watchdog|volt|throttl|pstore|ramoops|reset|fsck|orphan|not properly" | head -20
echo "== timesync"; journalctl -b 0 -o short-iso-precise --no-pager | grep -i -E "timesync|clock|time has been changed" | head -8
echo "== rauc"; rauc status 2>&1
echo "== fw_printenv"; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT 2>&1
'
echo "host_before=$(date +%s.%N)"
"${ssh[@]}" "$host" "$remote"
echo "host_after=$(date +%s.%N)"
