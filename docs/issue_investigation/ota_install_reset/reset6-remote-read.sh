# read-only board reads for reset 6; no writes, no sysctl. pstore is mounted
# read-only, every file copied byte-exact, then unmounted -- nothing in
# pstore is deleted.
echo "== uptime"; cat /proc/uptime
echo "== date"; date +%s.%N; date -Iseconds
echo "== dmesg iso head"; dmesg --time-format iso | head -n 1
echo "== boot_id"; cat /proc/sys/kernel/random/boot_id
echo "== rsts etc"; for f in rsts partition tryboot boot-mode; do printf '%s: ' $f; hexdump -v -e '4/1 "%02x"' /proc/device-tree/chosen/bootloader/$f 2>&1; echo; done
echo "== rauc status"; rauc status 2>&1
echo "== fw_printenv"; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT 2>&1
echo "== scheduler"; cat /sys/block/mmcblk0/queue/scheduler
echo "== cpufreq gov"; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
echo "== sysctls (expect none armed -- this was the baseline run, no diagnostics)"; for k in hung_task_timeout_secs hung_task_check_interval_secs hung_task_warnings printk_devkmsg; do printf '%s=' $k; cat /proc/sys/kernel/$k 2>&1; done
echo "== hb245 procs (expect 0 -- no heartbeat armed)"; ps | grep -c '[h]b245'
echo "== boots"; journalctl --list-boots --no-pager 2>&1 | tail -n 4
echo "== boot -1 last 25"; journalctl -b -1 -n 25 --no-pager -o short-iso-precise 2>&1
echo "== pstore mounts before"; grep -c pstore /proc/mounts
