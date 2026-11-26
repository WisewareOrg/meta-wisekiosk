#!/bin/bash
# Does the push rate track the AP-to-bench radio rate? <n> pushes of 30,000,000 B into wc -c (default
# cipher, as the test), each with the board's rx bitrate and the CPU line sampled every 2 s beside it,
# and the channel survey before and after. Then the bench soak log since 22 Nov 00:00 EST.
# Board reads only; nothing written, started or left running on the board. Output masked.
# usage: tst008-rate-track.sh <bench-host-or-ip> <out-file> [n]
set -u
board=$1
out=$2
n=${3:-4}
ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
          -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=10)
bytes=30000000
soak_since=1795323600  # 2026-11-22 00:00 EST
payload=$(mktemp)
trap 'rm -f "$payload" "$payload".*' EXIT
head -c "$bytes" /dev/urandom > "$payload"

mask() { sed -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/<mac>/g; s/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/<addr>/g; /SSID/d'; }
stamp() { date +%T.%N | cut -c1-12; }
survey() { ssh "${ssh_opts[@]}" "$board" "iw dev wlan0 survey dump 2>&1 | grep -A6 'in use' ; cat /proc/loadavg"; }
# 60 samples x 2 s bounds the sampler at 2 min; it is killed when the push ends
sampler='i=0; while [ $i -lt 60 ]; do t=$(cut -d" " -f1 /proc/uptime); r=$(iw dev wlan0 station dump | grep -E "rx bitrate|tx bitrate|tx failed" | tr -s "\t\n " "   "); c=$(top -b -n 1 | grep -m1 "^CPU:"); echo "$t $r | $c"; i=$((i+1)); sleep 2; done'

{
    echo "# rate track, $(date '+%F %T %Z'), $n pushes, default cipher"
    ssh "${ssh_opts[@]}" "$board" 'grep meta-wisekiosk /etc/buildinfo; cut -d" " -f1 /proc/uptime; cat /proc/sys/kernel/random/boot_id'
    for k in $(seq 1 "$n"); do
        echo "== $(stamp) push $k"
        echo "beside: containers: $(docker ps --format '{{.Names}}' | paste -sd, -); host load $(cut -d' ' -f1-3 /proc/loadavg)"
        echo "-- survey before"; survey
        ssh "${ssh_opts[@]}" "$board" "$sampler" > "$payload.s" 2>&1 &
        sp=$!
        sleep 2
        t0=$(date +%s.%N)
        counted=$(ssh "${ssh_opts[@]}" "$board" 'wc -c' < "$payload")
        t1=$(date +%s.%N)
        kill "$sp" 2>/dev/null; wait "$sp" 2>/dev/null
        echo "-- counted '$counted' (valid only if $bytes)"
        awk -v a="$t0" -v b="$t1" -v n="$bytes" 'BEGIN{printf "-- push wall %.1f s, %.3f MB/s (10^6 B)\n", b-a, n/(b-a)/1e6}'
        echo "-- board samples (uptime, rates, CPU) during push $k"; cat "$payload.s"
        echo "-- survey after"; survey
    done
    echo "== $(stamp) soak log since $soak_since"
    ssh "${ssh_opts[@]}" "$board" "wc -l /data/kiosk-soak.log; awk '{for(i=1;i<=NF;i++){split(\$i,kv,\"=\"); if(kv[1]==\"ts\" && kv[2]>=$soak_since) {print; next}}}' /data/kiosk-soak.log"
    echo "== $(stamp) done"
} 2>&1 | mask > "$out"
