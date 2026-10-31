# read-only board reads for reset 3; no writes, no mounts, no reboot
echo "== date/uptime"; date +%s; date -Iseconds; cat /proc/uptime
echo "== boot_id"; cat /proc/sys/kernel/random/boot_id
echo "== rsts etc"; for f in rsts partition tryboot boot-mode; do printf '%s: ' $f; hexdump -v -e '4/1 "%02x"' /proc/device-tree/chosen/bootloader/$f 2>&1; echo; done
echo "== uv"; for d in /sys/class/hwmon/hwmon*; do n=$(cat $d/name 2>/dev/null); [ "$n" = rpi_volt ] && echo "$d in0_lcrit_alarm=$(cat $d/in0_lcrit_alarm)"; done
echo "== dmesg voltage/hung/mmc/brcmf errors (current boot)"; dmesg | grep -i -E 'voltage|throttl|blocked for|mmc0: |sdhost.*(err|timeout)|brcmf.*(err|fail)|Booting Linux' | head -20
echo "== pstore mounts"; grep -c pstore /proc/mounts
echo "== sysctls"; for k in hung_task_timeout_secs hung_task_check_interval_secs hung_task_warnings printk_devkmsg panic; do printf '%s=' $k; cat /proc/sys/kernel/$k 2>&1; done
echo "== hb245 procs"; ps | grep -c '[h]b245'
echo "== rauc status"; rauc status 2>&1
echo "== fw_printenv"; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT 2>&1
echo "== boots"; journalctl --list-boots --no-pager 2>&1 | tail -3
echo "== journal boot -1 tail"; journalctl -b -1 -n 40 --no-pager -o short-iso-precise 2>&1
echo "== journal current boot head"; journalctl -b 0 --no-pager -o short-iso-precise 2>&1 | head -3
