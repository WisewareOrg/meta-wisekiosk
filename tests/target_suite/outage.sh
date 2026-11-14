#!/bin/sh
# Cut the board off the network, restore it, and keep a record. Usage: outage.sh OUTAGE_S GIVE_UP_S
# Pins the network to a BSSID no access point carries (memory only), un-pins after OUTAGE_S, and
# reboots at GIVE_UP_S after the un-pin if wlan0 still has no IPv4 address.
record=/tmp/test-outage.record
outage_s=$1
give_up_s=$2

uptime_s() {
    cut -d' ' -f1 /proc/uptime
}

wpa_state() {
    state=$(wpa_cli -i wlan0 status | sed -n 's/^wpa_state=//p')
    echo "${state:-UNKNOWN}"
}

has_ipv4() {
    if ip -4 -o addr show dev wlan0 | grep -q inet; then
        echo 1
    else
        echo 0
    fi
}

log() {
    echo "$*" | tee -a "$record"
}

trace() {
    log "trace $(uptime_s) $(wpa_state) has_ipv4=$(has_ipv4)"
}

reached() {
    awk -v now="$(uptime_s)" -v target="$1" 'BEGIN { exit !(now >= target) }'
}

id=$(wpa_cli -i wlan0 status | sed -n 's/^id=//p')
rm -f "$record"
log "id $id"

wpa_cli -i wlan0 set_network "$id" bssid ff:ff:ff:ff:ff:ff > /dev/null
wpa_cli -i wlan0 disconnect > /dev/null
wpa_cli -i wlan0 reconnect > /dev/null
cut_at=$(uptime_s)
log "cut $cut_at"

restore_at=$(awk -v t="$cut_at" -v s="$outage_s" 'BEGIN { print t + s }')
until reached "$restore_at"; do
    trace
    sleep 1
done

t0=$(uptime_s)
log "t0 $t0"
wpa_cli -i wlan0 set_network "$id" bssid any > /dev/null

give_up_at=$(awk -v t="$t0" -v s="$give_up_s" 'BEGIN { print t + s }')
while [ "$(has_ipv4)" = 0 ]; do
    if reached "$give_up_at"; then
        systemctl reboot
        exit 0
    fi
    trace
    sleep 1
done
trace
