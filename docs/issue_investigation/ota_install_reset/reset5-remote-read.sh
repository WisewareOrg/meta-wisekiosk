# read-only board reads for reset 5; no writes, no mounts, no reboot, no pstore access, no sysctl
echo "== uptime samples"; for i in $(seq 1 20); do cat /proc/uptime; sleep 0.2; done
echo "== date"; date +%s.%N; date -Iseconds
echo "== dmesg iso head"; dmesg --time-format iso | head -n 1
echo "== boot_id"; cat /proc/sys/kernel/random/boot_id
echo "== rsts etc"; for f in rsts partition tryboot boot-mode; do printf '%s: ' $f; hexdump -v -e '4/1 "%02x"' /proc/device-tree/chosen/bootloader/$f 2>&1; echo; done
echo "== uv"; for d in /sys/class/hwmon/hwmon*; do n=$(cat $d/name 2>/dev/null); [ "$n" = rpi_volt ] && echo "$d in0_lcrit_alarm=$(cat $d/in0_lcrit_alarm)"; done
echo "== thermal"; cat /sys/class/thermal/thermal_zone0/temp 2>&1
echo "== dmesg fault grep (current boot)"; dmesg | grep -i -E 'voltage|throttl|blocked for|watchdog|sdhost.*(err|timeout)|mmc[01]: (error|timeout|card|new)|brcmf.*(err|fail)|FAT-fs|EXT4-fs' | head -n 30
echo "== scheduler"; cat /sys/block/mmcblk0/queue/scheduler
echo "== pstore mounts"; grep -c pstore /proc/mounts
echo "== sysctls"; for k in hung_task_timeout_secs hung_task_check_interval_secs hung_task_warnings printk_devkmsg; do printf '%s=' $k; cat /proc/sys/kernel/$k 2>&1; done
echo "== dirty sysctls"; for k in dirty_ratio dirty_background_ratio dirty_bytes dirty_background_bytes dirty_expire_centisecs dirty_writeback_centisecs; do printf '%s=' $k; cat /proc/sys/vm/$k 2>&1; done
echo "== hb245 procs"; ps | grep -c '[h]b245'
echo "== rauc status"; rauc status 2>&1
echo "== fw_printenv"; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT 2>&1
echo "== watchdog0"; for f in timeout timeleft bootstatus status; do printf '%s=' $f; cat /sys/class/watchdog/watchdog0/$f 2>&1; done
systemctl show -p RuntimeWatchdogUSec -p RuntimeWatchdogPreUSec -p WatchdogDevice -p WatchdogLastPingTimestampMonotonic 2>&1
echo "== cpufreq gov"; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
echo "== boots"; journalctl --list-boots --no-pager 2>&1 | tail -n 4
echo "== boot -1 first line"; journalctl -b -1 --no-pager -o short-iso-precise 2>&1 | head -n 2
echo "== boot -2 last 4"; journalctl -b -2 -n 4 --no-pager -o short-iso-precise 2>&1
echo "== boot -1 last 25"; journalctl -b -1 -n 25 --no-pager -o short-iso-precise 2>&1
echo "== boot -1 non-hb since 04:05:40"; journalctl -b -1 --since '2026-11-01 04:05:40' --no-pager -o short-iso-precise 2>&1 | grep -v hb245 | head -n 60
echo "== boot -1 soak"; journalctl -b -1 -u kiosk-soak.service -u kiosk-soak.timer --no-pager -o short-iso-precise 2>&1 | tail -n 10
echo "== timers"; systemctl list-timers --all --no-pager 2>&1 | head -n 20
echo "== epoch end"; date +%s.%N
