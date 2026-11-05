#!/bin/sh
# #245 investigation-only heartbeat for batch 5: hb245-freq.sh plus four
# appended read-only fields, so a reset can be read against the hardware
# watchdog's own countdown and PID1's state. Existing fields and their order
# are unchanged from hb245-freq.sh; the new fields are appended, not
# inserted, and nothing is written to the watchdog. loop5.sh checks once
# that /sys/class/watchdog/watchdog0/timeleft exists and is readable before
# this script is ever started; this script does not re-check it.
# Once a second, writes the install's own [stats] fields, freq=, and the
# watchdog/PID1 fields to /dev/kmsg, so a line survives a watchdog reset in
# the pstore console record even when the network dies with the board. Dies
# at the run's reboot; nothing persists past it. Never shipped: loop5.sh
# writes this to the board's /tmp over ssh, one run at a time.
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
    wdt=$(cat /sys/class/watchdog/watchdog0/timeleft)
    # shellcheck disable=SC2046 # field 3 is state, field 12 is majflt (proc(5)); PID1's comm has no spaces on this image
    set -- $(cat /proc/1/stat)
    p1=$3
    p1majflt=${12}
    p1wchan=$(cat /proc/1/wchan 2>/dev/null)
    echo "<5>hb245 $u $m$l $k uv=$uv freq=$freq wdt=$wdt p1=$p1 p1wchan=$p1wchan p1majflt=$p1majflt" > /dev/kmsg
    sleep 1
done
