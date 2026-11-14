#!/bin/sh
# Type at an attached keyboard on the board, one gated phase at a time, and keep a record.
# Usage: keyboard.sh DEVICE_S X_OPENED_S CONSOLE_S SHELL_S MARKER_S
#        keyboard.sh --chord EVENTS_FILE   (a file name inside /tmp/test-keyboard)
# Creates a virtual keyboard from keyboard.desc, plays chord.events, login.events and
# command.events into it as each phase's condition holds, then removes it. Each phase writes
# `phase <name> <uptime>` to the record, or `timeout <name> <uptime>` and stops if its bound passes.
# `--chord` plays one events file into a new virtual keyboard and removes it.
dir=/tmp/test-keyboard
record=$dir/record
LD_LIBRARY_PATH=$dir
export LD_LIBRARY_PATH
holder=
node=

uptime_s() {
    cut -d' ' -f1 /proc/uptime
}

log() {
    echo "$*" | tee -a "$record"
}

reached() {
    awk -v now="$(uptime_s)" -v target="$1" 'BEGIN { exit !(now >= target) }'
}

# whether the condition that ends phase $1 holds
holds() {
    case $1 in
        device)
            node=$(sed -n 's|.*: \(/dev/input/event[0-9]*\)$|\1|p' "$dir/device.out")
            [ -n "$node" ]
            ;;
        x_opened)
            xorg=$(pidof Xorg)
            [ -n "$xorg" ] && holders_of "$node" | grep -qx "$xorg"
            ;;
        console)
            [ "$(fgconsole)" = 2 ] && grep -q 'login:' /dev/vcs2
            ;;
        shell)
            for pid in $(holders_of /dev/tty2); do
                [ "$(cat "/proc/$pid/comm" 2> /dev/null)" = sh ] && return 0
            done
            return 1
            ;;
        marker)
            [ -e "$dir/marker" ]
            ;;
    esac
}

# the pids that hold the file $1 open, one per line
holders_of() {
    for word in $(fuser "$1" 2> /dev/null); do
        echo "${word%%[!0-9]*}"
    done
}

# wait_for NAME BOUND_S: poll until phase NAME's condition holds or BOUND_S passes
wait_for() {
    limit=$(awk -v t="$(uptime_s)" -v s="$2" 'BEGIN { print t + s }')
    until holds "$1"; do
        if reached "$limit"; then
            log "timeout $1 $(uptime_s)"
            return 1
        fi
        sleep 0.2
    done
    log "phase $1 $(uptime_s)"
}

finish() {
    if [ -n "$holder" ]; then
        kill "$holder" 2> /dev/null
        wait "$holder" 2> /dev/null
    fi
    exit "${1:-0}"
}

play() {
    "$dir/evemu-play" "$node" < "$dir/$1"
}

start_device() {
    "$dir/evemu-device" "$dir/keyboard.desc" > "$dir/device.out" &
    holder=$!
    wait_for device "$1" || finish 1
}

if [ "$1" = --chord ]; then
    start_device 10
    play "${2:?usage: keyboard.sh --chord EVENTS_FILE}"
    finish 0
fi

device_s=${1:?usage: keyboard.sh DEVICE_S X_OPENED_S CONSOLE_S SHELL_S MARKER_S}
x_opened_s=${2:?}
console_s=${3:?}
shell_s=${4:?}
marker_s=${5:?}

rm -f "$record"
start_device "$device_s"
wait_for x_opened "$x_opened_s" || finish 1
play chord.events
wait_for console "$console_s" || finish 1
play login.events
if wait_for shell "$shell_s"; then
    log "prompt shell $(uptime_s)"
else
    if grep -q 'Password:' /dev/vcs2; then
        log "prompt password $(uptime_s)"
    else
        log "prompt none $(uptime_s)"
    fi
    finish 1
fi
sleep 1
play command.events
wait_for marker "$marker_s" || finish 1
finish 0
