# read-only board reads for reset 4, pass 2; no writes, no mounts, no reboot
i=0; while [ $i -lt 15 ]; do echo "UP $(cut -d' ' -f1 /proc/uptime)"; sleep 1; i=$((i+1)); done
echo "== dmesg iso head"; dmesg --time-format iso | head -n 1
echo "== timesync"; timedatectl show 2>&1 | grep -E 'NTP|Synchron'
echo "== journal boot -2 last 4"; journalctl -b -2 -n 4 --no-pager -o short-iso-precise 2>&1
echo "== journal boot -1 PID1 last 5"; journalctl -b -1 _PID=1 -n 5 --no-pager -o short-iso-precise 2>&1
echo "== journal boot -1 non-hb last 10"; journalctl -b -1 --no-pager -o short-iso-precise 2>&1 | grep -v hb245 | tail -n 10
echo "== systemd watchdog"; systemctl show -p RuntimeWatchdogUSec -p RuntimeWatchdogPreUSec -p WatchdogDevice 2>&1
ls /sys/class/watchdog/watchdog0/ 2>&1; for f in timeleft pretimeout identity; do printf '%s=' $f; cat /sys/class/watchdog/watchdog0/$f 2>&1; done
echo "== iosched"; cat /sys/block/mmcblk0/queue/scheduler 2>&1; cat /sys/block/mmcblk0/queue/nr_requests 2>&1
