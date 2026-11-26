#!/bin/bash
# Host-side, read only: every 2.5 s for <seconds>, the TCP state (ss -ti) of each established
# connection from this host to <board> port <port>. Run beside a push (A96 step 2 or 4).
# Addresses are masked in the output.
# usage: tst008-ss-sample.sh <board-host-or-ip> <seconds> [port]
set -u
board=${1#*@}
seconds=${2:-120}
port=${3:-22}
ip=$(getent ahostsv4 "$board" | awk 'NR==1{print $1}')
[[ -n $ip ]] || ip=$board
end=$(( $(date +%s) + seconds ))
while (( $(date +%s) < end )); do
    printf '== %s\n' "$(date +%T.%N | cut -c1-12)"
    ss -tinH state established dst "$ip" dport = ":$port" \
        | sed -E 's/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/<addr>/g; s/[[:space:]]+/ /g'
    sleep 2.5
done
