# read-only board reads for reset 7; no writes, no mounts, no reboot, no pstore access, no sysctl writes
echo "== uptime samples"; for i in $(seq 1 20); do cat /proc/uptime; sleep 0.2; done
echo "== date"; date +%s.%N; date -Iseconds
echo "== uname"; uname -a
echo "== dmesg iso head"; dmesg --time-format iso | head -n 1
echo "== boot_id"; cat /proc/sys/kernel/random/boot_id
echo "== rsts etc"; for f in rsts partition tryboot boot-mode; do printf '%s: ' $f; hexdump -v -e '4/1 "%02x"' /proc/device-tree/chosen/bootloader/$f 2>&1; echo; done
echo "== uv"; for d in /sys/class/hwmon/hwmon*; do n=$(cat $d/name 2>/dev/null); [ "$n" = rpi_volt ] && echo "$d in0_lcrit_alarm=$(cat $d/in0_lcrit_alarm)"; done
echo "== thermal"; cat /sys/class/thermal/thermal_zone0/temp 2>&1
echo "== lockup sysctls"; for k in watchdog soft_watchdog nmi_watchdog watchdog_thresh watchdog_cpumask softlockup_panic softlockup_all_cpu_backtrace panic panic_on_oops panic_print hung_task_panic tainted sysrq; do printf '%s=' $k; cat /proc/sys/kernel/$k 2>&1; done
echo "== sched rt"; for k in sched_rt_runtime_us sched_rt_period_us; do printf '%s=' $k; cat /proc/sys/kernel/$k 2>&1; done
echo "== ls /proc/sys/kernel lockup-ish"; ls /proc/sys/kernel | grep -i -E 'watchdog|lockup|hung|panic'
echo "== cmdline"; cat /proc/cmdline
echo "== ramoops params"; for f in /sys/module/ramoops/parameters/*; do printf '%s=' ${f##*/}; cat $f 2>&1; done
echo "== dmesg watchdog/lockup/pstore grep"; dmesg | grep -i -E 'watchdog|lockup|nmi|ramoops|pstore'
echo "== dmesg fault grep (current boot)"; dmesg | grep -i -E 'voltage|throttl|blocked for|sdhost.*(err|timeout)|mmc[01]: (error|timeout|card|new)|brcmf.*(err|fail)|FAT-fs|EXT4-fs' | head -n 30
echo "== modules dir"; ls /lib/modules/ 2>&1; find /lib/modules/$(uname -r) -name '*.ko*' 2>/dev/null | grep -i -E 'lkdtm|lockup|test' ; echo "ko count: $(find /lib/modules/$(uname -r) -name '*.ko*' 2>/dev/null | wc -l)"
echo "== config.gz"; ls -la /proc/config.gz 2>&1
echo "== scheduler"; cat /sys/block/mmcblk0/queue/scheduler
echo "== pstore mounts"; grep -c pstore /proc/mounts
echo "== sysctls"; for k in hung_task_timeout_secs hung_task_check_interval_secs hung_task_warnings printk_devkmsg; do printf '%s=' $k; cat /proc/sys/kernel/$k 2>&1; done
echo "== hb245 procs"; ps | grep -c '[h]b245'
echo "== rauc status"; rauc status 2>&1
echo "== fw_printenv"; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT 2>&1
echo "== buildinfo"; cat /etc/buildinfo 2>&1 | head -n 5
echo "== watchdog0"; for f in timeout timeleft bootstatus status; do printf '%s=' $f; cat /sys/class/watchdog/watchdog0/$f 2>&1; done
systemctl show -p RuntimeWatchdogUSec -p RuntimeWatchdogPreUSec -p WatchdogDevice 2>&1
echo "== cpufreq gov"; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
echo "== boots"; journalctl --list-boots --no-pager 2>&1 | tail -n 4
echo "== boot -1 first line"; journalctl -b -1 --no-pager -o short-iso-precise 2>&1 | head -n 2
echo "== boot -2 last 4"; journalctl -b -2 -n 4 --no-pager -o short-iso-precise 2>&1
echo "== boot -1 last 12"; journalctl -b -1 -n 12 --no-pager -o short-iso-precise 2>&1
echo "== boot -1 non-hb since 02:51:00"; journalctl -b -1 --since '2026-11-02 02:51:00' --no-pager -o short-iso-precise 2>&1 | grep -v hb245 | head -n 60
echo "== boot -1 soak"; journalctl -b -1 -u kiosk-soak.service --no-pager -o short-iso-precise 2>&1 | tail -n 4
echo "== epoch end"; date +%s.%N
