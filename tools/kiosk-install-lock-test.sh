#!/usr/bin/env bash
# Self-test for the per-board install lock in tools/kiosk-install.sh.
#
#   tools/kiosk-install-lock-test.sh
#
# Runs the SHIPPED script (or the one named by KIOSK_INSTALL_UNDER_TEST) from a scratch checkout with stubs for
# ssh, docker, curl, getent and the reproducibility gate first on PATH. The stub ssh answers the reads, blocks
# `rauc install` until the test releases it, and leaves the streaming commands sleeping. Cases are judged from
# a log of what each call reached, and from polls that are bounded; nothing is judged by elapsed time.
#
# Cases: a second call to one board is refused before any ssh and names the holder; the first ends normally; a
# call to another board goes on; the lock is free after the first ends or is killed whole; a script killed alone
# frees the lock at once although its streaming ssh sessions live on (rauc goes on installing, and a later call is
# refused by rauc only, after its arming; the real ssh closes the descriptor, so the lock cannot outlive the script); no streaming ssh is left after a normal end; callers with different XDG_RUNTIME_DIR meet on one lock; two names for one address meet, another address
# does not, and a name that does not resolve is keyed as typed (user stripped).
#
# TO WATCH THIS FAIL, with KIOSK_INSTALL_UNDER_TEST=<a copy of the script with one seed>:
#   * delete the `flock -n 8` condition: "a second call is refused"
#   * delete `exec 8>&-` in stream(): "a script killed alone frees the lock"
#   * leave out `exec` before the stream's ssh: "none of its streaming ssh is left"
#   * key the lock on "$host" as typed: "two names for one address meet"
#   * put XDG_RUNTIME_DIR into the lock path: "other environments meet on one lock"
#
# Exit: 0 every case passed; 1 a case failed.
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
shipped=${KIOSK_INSTALL_UNDER_TEST:-$root/tools/kiosk-install.sh}
scratch=$(mktemp -d)
tag=lt$$
cleanup() {
    local f
    jobs -p | xargs -r kill -9 2>/dev/null
    for f in "$scratch"/pg.*; do kill -9 -- "-$(cat "$f")" 2>/dev/null; done
    rm -f /tmp/kiosk-install-*"$tag"*.lock /tmp/kiosk-install-ADDR-*"$tag"*.lock
    rm -rf "$scratch"
}
trap cleanup EXIT
mkdir -p "$scratch/co/tools" "$scratch/bin" "$scratch/state"
export LOG=$scratch/log STATE=$scratch/state RELEASE=$scratch/release
: > "$LOG"
cp "$shipped" "$scratch/co/tools/kiosk-install.sh"
printf '#!/bin/sh\nexit 0\n' > "$scratch/co/tools/reproducibility-gate.sh"
: > "$scratch/co/tools/kiosk-install-ftrace-filter.txt"
chmod +x "$scratch/co/tools/"*.sh
touch "$scratch/bundle.raucb"

cat > "$scratch/bin/ssh" <<'STUB'
#!/bin/bash
exec 8>&-
cmd="${*: -1}"
echo "$CALL ssh $(printf '%s' "$*" | tr '\n' ' ' | cut -c1-400)" >> "$LOG"
case "$*" in
    -G*) case "$2" in alias-one-*) echo "hostname board-one-$TAGNAME.invalid" ;; *) echo "hostname $2" ;; esac; exit 0 ;;
esac
case "$cmd" in
    *fw_printenv*) if [ -e "$STATE/installed" ]; then printf 'BOOT_ORDER=B A\nBOOT_A_LEFT=0\nBOOT_B_LEFT=3\nBooted from: rootfs.0 (A)\n'
                   else printf 'BOOT_ORDER=A B\nBOOT_A_LEFT=3\nBOOT_B_LEFT=3\nBooted from: rootfs.0 (A)\n'; fi ;;
    *'date +%s'*) date +%s ;;
    *SSH_CLIENT*) echo local ;;
    *boot_id*) echo bootid ;;
    *'rauc install'*) for _ in $(seq 1 600); do [ -e "$RELEASE" ] && break; sleep 0.1; done; touch "$STATE/installed" ;;
    *'dmesg -w'*|*'journalctl -f'*|*'while true'*) echo $$ >> "$STATE/streams.$CALL"; exec sleep 600 ;;
    *) echo ok ;;
esac
STUB
cat > "$scratch/bin/docker" <<'STUB'
#!/bin/bash
echo "$CALL docker $1" >> "$LOG"
case "$1" in
    run) echo cid ;;
    port) echo "0.0.0.0:5555" ;;
    exec) cat > /dev/null ;;
    ps) ;;
esac
exit 0
STUB
cat > "$scratch/bin/getent" <<'STUB'
#!/bin/bash
case "$2" in
    board-one-*) echo "ADDR-ONE-$TAGNAME STREAM $2" ;;
    board-two-*) echo "ADDR-TWO-$TAGNAME STREAM $2" ;;
esac
exit 0
STUB
printf '#!/bin/sh\nexit 0\n' > "$scratch/bin/curl"
chmod +x "$scratch/bin/"*
export PATH=$scratch/bin:$PATH TAGNAME=$tag

fails=0
check() { local name=$1; shift; if "$@"; then echo "ok    $name"; else echo "FAIL  $name"; fails=$((fails + 1)); fi; }
not() { ! "$@"; }
reached() { grep -q "^$1 $2" "$LOG"; }
await() {
    local _
    for _ in $(seq 1 150); do "$@" && return 0; sleep 0.1; done
    echo "FAIL  never reached: $*"
    exit 1
}
install() { # call-id host: one install in the background, in a session of its own, its output in out.<id>
    local id=$1 host=$2
    # shellcheck disable=SC2016 # the inner shell expands its own arguments
    (cd "$scratch/co" && exec setsid bash -c 'echo $$ > "$1"; env CALL="$2" tools/kiosk-install.sh "$3" "$4" > "$5" 2>&1; echo $? > "$6"' \
        _ "$scratch/pg.$id" "$id" "$host" "$scratch/bundle.raucb" "$scratch/out.$id" "$scratch/rc.$id") &
    await test -s "$scratch/pg.$id"
}
one="root@board-one-$tag.invalid"
two="root@board-two-$tag.invalid"
alias1="root@alias-one-$tag.invalid"
rcof() { cat "$scratch/rc.$1" 2>/dev/null; }

# 1. a second call to one board is refused, names the holder, and reached nothing but `ssh -G`
rm -f "$RELEASE" "$STATE/installed"
install 1 "$one"
await reached 1 "docker run"
(cd "$scratch/co" && CALL=2 tools/kiosk-install.sh "$one" "$scratch/bundle.raucb" > "$scratch/out.2" 2>&1; echo $? > "$scratch/rc.2")
refused() { [ "$(rcof 2)" = 1 ] && grep -q "another install holds $one" "$scratch/out.2" && grep -q "[0-9] $scratch/co" "$scratch/out.2"; }
check "a second call is refused and names the holder" refused
only_g() { ! grep "^$1 " "$LOG" | grep -v ' ssh -G' | grep -q .; }
check "the refused call reached nothing but ssh -G" only_g 2
# 3. a call to another board goes on, and a call with another XDG_RUNTIME_DIR to the first board is refused
install 3 "$two"
await reached 3 "docker run"
check "another board goes on" reached 3 "docker run"
mkdir -p "$scratch/xdg"
(cd "$scratch/co" && CALL=4 XDG_RUNTIME_DIR="$scratch/xdg" tools/kiosk-install.sh "$one" "$scratch/bundle.raucb" > /dev/null 2>&1; echo $? > "$scratch/rc.4")
check "other environments meet on one lock" test "$(rcof 4)" = 1
check "that call reached nothing but ssh -G" only_g 4
# 5. two names for one address meet; a name that does not resolve is keyed as typed
(cd "$scratch/co" && CALL=5 tools/kiosk-install.sh "$alias1" "$scratch/bundle.raucb" > /dev/null 2>&1; echo $? > "$scratch/rc.5")
check "two names for one address meet" test "$(rcof 5)" = 1
check "that call reached nothing but ssh -G" only_g 5
# a name that does not resolve is keyed as typed, user stripped: two users on it meet
install 11 "root@nores-$tag.invalid"
await reached 11 "docker run"
(cd "$scratch/co" && CALL=12 tools/kiosk-install.sh "admin@nores-$tag.invalid" "$scratch/bundle.raucb" > /dev/null 2>&1; echo $? > "$scratch/rc.12")
check "a name that does not resolve is keyed with the user stripped" test "$(rcof 12)" = 1
check "that call reached nothing but ssh -G" only_g 12
touch "$RELEASE"
await test -e "$scratch/rc.1"
check "the first call ends normally" test "$(rcof 1)" = 0
disarmed_once() { [ "$(grep -c '^1 ssh .*echo 0 > /sys/kernel/debug/pstore/record_ftrace' "$LOG")" -eq 1 ]; }
check "the first call disarmed its recorders once" disarmed_once
await test -e "$scratch/rc.3"
await test -e "$scratch/rc.11"
none_alive() {
    local p
    [ -s "$STATE/streams.1" ] || return 1
    while read -r p; do
        ! kill -0 "$p" 2>/dev/null || return 1
    done < "$STATE/streams.1"
}
check "after the script ends none of its streaming ssh is left" none_alive

# 6. free after one killed whole
rm -f "$RELEASE" "$STATE/installed"; : > "$LOG"
install 6 "$one"
await reached 6 "docker run"
kill -9 -- "-$(cat "$scratch/pg.6")" 2>/dev/null
await not kill -0 -- "-$(cat "$scratch/pg.6")"
install 7 "$one"
await reached 7 "docker run"
check "the lock is free after the first ended and after one killed whole" reached 7 "docker run"
kill -9 -- "-$(cat "$scratch/pg.7")" 2>/dev/null
await not kill -0 -- "-$(cat "$scratch/pg.7")"

# 7. a script killed alone frees the lock at once, though its streaming ssh live on: the next call goes
: > "$LOG"; rm -f "$RELEASE" "$STATE/installed"
install 8 "$one"
await reached 8 "docker run"
await reached 8 "ssh .*dmesg -w"
script=$(pgrep -P "$(cat "$scratch/pg.8")" | head -n 1)
check "the script of call 8 was found" test -n "$script"
kill -9 "${script:-0}" 2>/dev/null
await not kill -0 "${script:-0}"
install 10 "$one"
await reached 10 "docker run"
check "a script killed alone frees the lock though its streaming ssh live on" reached 10 "docker run"

echo "kiosk-install lock: $fails case(s) failed"
[ "$fails" -eq 0 ]
