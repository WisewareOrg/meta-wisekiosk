# read-only board reads for reset 3, pass 2; no writes, no mounts, no reboot
echo "== epoch/uptime x3"; for i in 1 2 3; do date +%s.%N; cat /proc/uptime; done
echo "== dmesg iso head"; dmesg --time-format iso | head -n 2
echo "== cmdline devkmsg / hung / watchdog tokens"; tr ' ' '\n' < /proc/cmdline | grep -E 'devkmsg|hung|watchdog|panic|loglevel|console'
echo "== dmesg current boot fault grep"; dmesg | grep -i -E 'voltage|throttl|blocked for|mmc0: |sdhost|brcmf.*(err|fail)|Booting Linux|FAT-fs|suppressed' | head -n 20
echo "== journal current boot head"; journalctl -b 0 --no-pager -o short-iso-precise 2>&1 | head -n 3
echo "== journal current boot timesync"; journalctl -b 0 --no-pager -o short-iso-precise 2>&1 | grep -i -E 'time.*synchron|clock' | head -n 5
echo "== watchdog0"; for f in timeout bootstatus; do printf '%s=' $f; cat /sys/class/watchdog/watchdog0/$f 2>&1; done
