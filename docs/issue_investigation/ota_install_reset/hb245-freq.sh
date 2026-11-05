#!/bin/sh
# #245 investigation-only heartbeat for batch 4: hb245.sh plus one appended
# field, the live CPU frequency, so a reset can be read against whether the
# core was pinned at its capped frequency. Existing fields and their order
# are unchanged from hb245.sh; freq= is appended, not inserted. Once a
# second, writes the install's own [stats] fields plus freq= to /dev/kmsg,
# so a line survives a watchdog reset in the pstore console record even when
# the network dies with the board. Dies at the run's reboot; nothing
# persists past it. Never shipped: loop4.sh writes this to the board's /tmp
# over ssh, one run at a time.
h=
for d in /sys/class/hwmon/hwmon*; do
    [ "$(cat "$d"/name 2>/dev/null)" = rpi_volt ] && h="$d"
done
while true; do
    u=$(cut -d' ' -f1 /proc/uptime)
    m=
    for f in MemFree Dirty Writeback; do
        # shellcheck disable=SC2046 # word splitting is the point: fields into $1 $2 $3...
        set -- $(grep "^$f:" /proc/meminfo)
        m="$m$1$2 "
    done
    # shellcheck disable=SC2046
    set -- $(cat /proc/loadavg)
    l="load=$1 $2 $3"
    # shellcheck disable=SC2046
    set -- $(cat /sys/block/mmcblk0/stat)
    k="mmc=$*"
    uv=$(cat "$h/in0_lcrit_alarm")
    freq=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)
    echo "<5>hb245 $u $m$l $k uv=$uv freq=$freq" > /dev/kmsg
    sleep 1
done
