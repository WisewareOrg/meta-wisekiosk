#!/bin/bash
# #408: watch one board's radio link every 10 s for 10 min, read only (no push, nothing started that
# outlives the ssh). Run once per board at the same time, from the host, one output file each.
# Each line: host clock, board uptime, rx/tx bitrate, tx failed, signal, frequency, loadavg.
# usage: radio-watch.sh <board-host-or-ip> <role: bench|prod> <out-file> [samples]
# Output is written line by line (sed -u), so a kill keeps every sample read so far.
set -u
board=$1
role=$2
out=$3
samples=${4:-60}
ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
          -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=10 -o ServerAliveInterval=15)
mask() { sed -u -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/<mac>/g; s/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/<addr>/g; /SSID/d'; }
reader="i=0; while [ \$i -lt $samples ]; do u=\$(cut -d' ' -f1 /proc/uptime); s=\$(iw dev wlan0 station dump | grep -E 'rx bitrate|tx bitrate|tx failed|signal:' | tr -s '\t\n ' '   '); f=\$(iw dev wlan0 link | grep -m1 freq | tr -s '\t ' ' '); l=\$(cut -d' ' -f1-3 /proc/loadavg); echo \"\$u | \$s | \$f | load \$l\"; i=\$((i+1)); sleep 10; done"
{
    echo "# radio watch, $role, $(date '+%F %T %Z'), $samples x 10 s"
    ssh "${ssh_opts[@]}" "$board" 'grep meta-wisekiosk /etc/buildinfo; cat /proc/sys/kernel/random/boot_id'
    ssh "${ssh_opts[@]}" "$board" "$reader" | while IFS= read -r line; do printf '%s %s\n' "$(date +%T)" "$line"; done
    echo "# done $(date +%T)"
} 2>&1 | mask > "$out"
