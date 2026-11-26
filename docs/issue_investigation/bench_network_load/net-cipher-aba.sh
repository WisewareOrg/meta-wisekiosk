#!/bin/bash
# rule: cipher A/B/A on the bench, then today's soak-log lines. Board reads only; nothing written,
# started or left running on the board. Output masks addresses and MACs.
# usage: tst008-cipher-aba.sh <bench-host-or-ip> <out-file>
set -u
board=$1
out=$2
here=$(dirname "$(readlink -f "$0")")
ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
          -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=10)
bytes=30000000
day_start=1795582800  # 2026-11-25 00:00 EST
payload=$(mktemp)
trap 'rm -f "$payload"' EXIT
head -c "$bytes" /dev/urandom > "$payload"

mask() { sed -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/<mac>/g; s/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/<addr>/g; /SSID/d'; }
stamp() { date +%T.%N | cut -c1-12; }
beside() { echo "beside: $(docker ps --format '{{.Names}}' | paste -sd, -); host load $(cut -d' ' -f1-3 /proc/loadavg)"; }
station() {
    ssh "${ssh_opts[@]}" "$board" \
        "iw dev wlan0 station dump | grep -E 'rx bytes|rx packets|tx packets|tx retries|tx failed|signal:|tx bitrate|rx bitrate'; cat /proc/loadavg"
}

arm() {  # arm <name> [ssh cipher option...]
    local name=$1; shift
    echo "== $(stamp) arm $name: push $bytes B into wc -c ${*:-(default cipher)}"
    beside
    echo "-- station before"; station
    "$here/tst008-ss-sample.sh" "$board" 120 > "$payload.ss" 2>&1 &
    local ss_pid=$!
    ssh "${ssh_opts[@]}" "$board" 'top -b -n 4 -d 5 | head -n 12' > "$payload.top" 2>&1 &
    local top_pid=$!
    local t0 t1 counted
    t0=$(date +%s.%N)
    counted=$(ssh "${ssh_opts[@]}" "$@" "$board" 'wc -c' < "$payload")
    t1=$(date +%s.%N)
    wait "$top_pid"
    kill "$ss_pid" 2>/dev/null; wait "$ss_pid" 2>/dev/null
    echo "-- counted '$counted' (valid only if $bytes)"
    awk -v a="$t0" -v b="$t1" -v n="$bytes" 'BEGIN{printf "-- push wall %.1f s, %.3f MB/s (10^6 B)\n", b-a, n/(b-a)/1e6}'
    echo "-- station after"; station
    echo "-- board top (all processes)"; cat "$payload.top"
    echo "-- ss during arm $name"; cat "$payload.ss"
    beside
}

{
    echo "# rule cipher A/B/A, $(date '+%F %T %Z')"
    ssh "${ssh_opts[@]}" "$board" 'grep meta-wisekiosk /etc/buildinfo; cut -d" " -f1 /proc/uptime; cat /proc/sys/kernel/random/boot_id'
    arm A1
    arm B -c aes128-ctr
    arm A2
    echo "== $(stamp) soak log, lines since $day_start"
    ssh "${ssh_opts[@]}" "$board" \
        "awk '{for(i=1;i<=NF;i++){split(\$i,kv,\"=\"); if(kv[1]==\"ts\" && kv[2]>=$day_start) {print; next}}}' /data/kiosk-soak.log"
    echo "== $(stamp) done"
} 2>&1 | mask > "$out"
rm -f "$payload.ss" "$payload.top"
