# read-only board reads for reset 4; no writes, no mounts, no reboot, no pstore access
echo "== date/uptime x2"; for i in 1 2; do date +%s.%N; cat /proc/uptime; done
echo "== dmesg iso head"; dmesg --time-format iso | head -n 1
echo "== boot_id"; cat /proc/sys/kernel/random/boot_id
echo "== rsts etc"; for f in rsts partition tryboot boot-mode; do printf '%s: ' $f; hexdump -v -e '4/1 "%02x"' /proc/device-tree/chosen/bootloader/$f 2>&1; echo; done
echo "== uv"; for d in /sys/class/hwmon/hwmon*; do n=$(cat $d/name 2>/dev/null); [ "$n" = rpi_volt ] && echo "$d in0_lcrit_alarm=$(cat $d/in0_lcrit_alarm)"; done
echo "== dmesg fault grep (current boot)"; dmesg | grep -i -E 'voltage|throttl|blocked for|sdhost.*(err|timeout)|mmc[01]: (error|timeout|card|new)|brcmf.*(err|fail)|power save|Booting Linux|FAT-fs' | head -n 20
echo "== pstore mounts"; grep -c pstore /proc/mounts
echo "== sysctls"; for k in hung_task_timeout_secs hung_task_check_interval_secs hung_task_warnings printk_devkmsg; do printf '%s=' $k; cat /proc/sys/kernel/$k 2>&1; done
echo "== hb245 procs"; ps | grep -c '[h]b245'
echo "== rauc status"; rauc status 2>&1
echo "== fw_printenv"; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT 2>&1
echo "== boots"; journalctl --list-boots --no-pager 2>&1 | tail -n 3
echo "== journal boot -1 last 3"; journalctl -b -1 -n 3 --no-pager -o short-iso-precise 2>&1
echo "== watchdog0"; for f in timeout bootstatus; do printf '%s=' $f; cat /sys/class/watchdog/watchdog0/$f 2>&1; done
echo "== cpufreq"; C=/sys/devices/system/cpu/cpu0/cpufreq
for f in scaling_driver scaling_governor scaling_available_governors scaling_available_frequencies scaling_min_freq scaling_max_freq scaling_cur_freq cpuinfo_min_freq cpuinfo_max_freq cpuinfo_cur_freq; do printf '%s=' $f; cat $C/$f 2>&1; done
ls -l $C/scaling_max_freq $C/scaling_min_freq $C/scaling_setspeed 2>&1; printf 'scaling_setspeed='; cat $C/scaling_setspeed 2>&1
ls $C/stats 2>&1 | head; cat $C/stats/time_in_state 2>&1; printf 'total_trans='; cat $C/stats/total_trans 2>&1
echo "== kiosk-cpufreq-cap"; systemctl is-active kiosk-cpufreq-cap.service 2>&1; systemctl is-enabled kiosk-cpufreq-cap.service 2>&1
echo "== vcgencmd"; command -v vcgencmd && { vcgencmd measure_clock arm; vcgencmd get_throttled; vcgencmd measure_volts core; vcgencmd measure_temp; } 2>&1
echo "== thermal"; cat /sys/class/thermal/thermal_zone0/temp 2>&1
echo "== debugfs"; grep debugfs /proc/mounts; grep -w debugfs /proc/filesystems; ls -ld /sys/kernel/debug 2>&1
echo "== config.gz"; ls -l /proc/config.gz 2>&1
echo "== mmc hosts"; for h in /sys/class/mmc_host/mmc*; do echo "$h -> $(readlink -f $h/device) driver=$(basename $(readlink -f $h/device/driver))"; ls $h | grep -E '^mmc[0-9]:' | while read c; do echo "  card $c type=$(cat $h/$c/type 2>&1) name=$(cat $h/$c/name 2>&1)"; done; done
echo "== debugfs mmc"; for m in mmc0 mmc1; do echo "-- $m"; ls -l /sys/kernel/debug/$m 2>&1 | head -n 20; printf 'clock='; cat /sys/kernel/debug/$m/clock 2>&1; echo "ios:"; cat /sys/kernel/debug/$m/ios 2>&1; printf 'caps='; cat /sys/kernel/debug/$m/caps 2>&1; done
echo "== dt mmc nodes"; for n in /proc/device-tree/soc/mmc* /proc/device-tree/soc/sdhci*; do [ -d "$n" ] || continue; echo "-- $n status=$(tr -d '\0' < $n/status 2>/dev/null) compat=$(tr '\0' ' ' < $n/compatible 2>/dev/null)"; for p in brcm,overclock-50 max-frequency bus-width clock-frequency non-removable brcm,pio-limit; do [ -e "$n/$p" ] && printf '  %s=%s\n' $p "$(hexdump -v -e '4/1 "%02x"' $n/$p)"; done; done
echo "== module params"; for m in sdhost_bcm2835 mmc_bcm2835 brcmfmac mmc_core; do [ -d /sys/module/$m/parameters ] && for p in /sys/module/$m/parameters/*; do printf '%s=%s\n' "$p" "$(cat $p 2>&1)"; done; done
echo "== wifi"; command -v iw; iw dev wlan0 get power_save 2>&1; iw dev wlan0 info 2>&1 | grep -v -i -E 'addr|ssid'; ls /sys/class/net/wlan0/device/driver 2>&1 | head -n 3; readlink -f /sys/class/net/wlan0/device 2>&1
echo "== epoch end"; date +%s.%N
