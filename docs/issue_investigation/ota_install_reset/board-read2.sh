#!/bin/bash
# Read-only follow-up: pstore archive, ramoops boot messages, clock alignment, kernel start time.
host="root@$1"
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o LogLevel=ERROR)
# shellcheck disable=SC2016
remote='
echo "== pstore archive"; ls -laR /var/lib/systemd/pstore 2>&1 | head -n 30
echo "== pstore unit"; systemctl show -p ActiveState,Result,ConditionResult,ExecMainStartTimestamp systemd-pstore.service 2>&1; cat /etc/systemd/pstore.conf 2>&1 | grep -v "^#" ; ls /etc/systemd/pstore.conf.d 2>&1
for b in 0 -1 -2; do echo "== pstore unit journal b=$b"; journalctl -b $b -u systemd-pstore -o short-iso-precise --no-pager 2>&1 | tail -n 5; done
echo "== ramoops/pstore/wdt in dmesg (current boot)"; dmesg --time-format iso | grep -i -E "ramoops|pstore|watchdog|wdt|volt|throttl|Booting Linux" | head -n 20
echo "== ramoops/pstore in boot -1 kernel"; journalctl -b -1 -k -o short-iso-precise --no-pager | grep -i -E "ramoops|pstore|Booting Linux|watchdog" | head -n 10
echo "== timesync b0"; journalctl -b 0 -o short-iso-precise --no-pager | grep -i -E "timesync|time has been changed|clock" | head -n 10
echo "== b0 first lines"; journalctl -b 0 -o short-iso-precise --no-pager | head -n 4
echo "== edges"; s=$(date +%s); n=0; while [ $n -lt 3 ]; do t=$(date +%s); if [ "$t" != "$s" ]; then echo "edge $t $(cat /proc/uptime)"; s=$t; n=$((n+1)); fi; done
'
"${ssh[@]}" "$host" "$remote" | while IFS= read -r l; do printf '%s %s\n' "$(date +%s.%N)" "$l"; done
