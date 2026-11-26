#!/usr/bin/env bash
# Self-test, from this host, for tools/kiosk-install.sh: the per-board install lock, the bundle server's
# stale-server sweep and port read, and the real ssh's handling of an inherited descriptor.
#
#   tools/kiosk-install-lock-test.sh
#
# Runs the SHIPPED script (or the one named by KIOSK_INSTALL_UNDER_TEST) from a scratch checkout with stubs for
# ssh, docker, curl, getent and the reproducibility gate first on PATH. The stub ssh answers the reads, blocks
# `rauc install` until the test releases it, and leaves the streaming commands sleeping. Cases are judged from
# a log of what each call reached, and from polls that are bounded; nothing is judged by elapsed time.
#
# TO WATCH THIS FAIL, with KIOSK_INSTALL_UNDER_TEST=<a copy of the script with one seed>; each prints these
# lines and ends within the timeout tools/ci-guards.sh gives this test (a call that must be refused is bounded at 5 s):
#   * make the `flock -n 8` condition always false: "a second call is refused and names the holder"
#   * delete `exec 8>&-` in stream(): "a script killed alone frees the lock though its streaming ssh live on"
#   * leave out `exec` before the stream's ssh: "after the script ends none of its streaming ssh is left"
#   * key the lock on "$host" as typed: "a name that ssh -G maps to the board's own meets its lock" and
#     "a name that only getent maps to the board's address meets its lock"
#   * put XDG_RUNTIME_DIR into the lock path: "other environments meet on one lock"
#   * take no address from getent: "a name that only getent maps to the board's address meets its lock"
#   * take no HostName from ssh -G: "a name that ssh -G maps to the board's own meets its lock"
#   * drop `ps -p "$owner" >/dev/null 2>&1 ||` in serve(): "a server whose pid is dead is removed and one whose pid is alive is kept"
#   * drop `port=${port##*:}` in serve(): "the port is the one on a two-line docker port"
#   * in a scratch copy of this test, run `bash -c 'sleep 3'` in place of ssh in ssh_closes_fd8: the run stops at "never reached: has_child";
#     and set real_ssh to a script named ssh holding `#!/bin/bash` and `sleep 3 & wait`, which keeps the descriptor:
#     "the real ssh closes a descriptor it inherits", with the file's fd named. The stub ssh's own `exec 8>&-` stays.
#
# Exit: 0 every case passed; 1 a case failed.
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
shipped=${KIOSK_INSTALL_UNDER_TEST:-$root/tools/kiosk-install.sh}
scratch=$(mktemp -d)
tag=lt$$
cleanup() {
    local f status=$?
    jobs -p | xargs -r kill -9 2>/dev/null
    for f in "$scratch"/pg.*; do kill -9 -- "-$(cat "$f")" 2>/dev/null; done
    rm -f /tmp/kiosk-install-*"$tag"*.lock
    if [ "$status" -ne 0 ]; then echo "scratch kept: $scratch"; else rm -rf "$scratch"; fi
}
trap cleanup EXIT
trap 'exit 143' TERM
mkdir -p "$scratch/co/tools" "$scratch/bin" "$scratch/state" "$scratch/home"
export HOME=$scratch/home
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
echo "$CALL docker $*" >> "$LOG"
case "$1" in
    run) echo cid ;;
    port) if [ -s "$STATE/port.out" ]; then cat "$STATE/port.out"; else echo "0.0.0.0:5555"; fi ;;
    exec) cat > /dev/null ;;
    ps) cat "$STATE/ps.list" 2>/dev/null ;;
esac
exit 0
STUB
cat > "$scratch/bin/getent" <<'STUB'
#!/bin/bash
case "$2" in
    board-one-*) echo "ADDR-ONE-$TAGNAME STREAM $2" ;;
    board-two-*) echo "ADDR-TWO-$TAGNAME STREAM $2" ;;
    third-one-*) echo "ADDR-ONE-$TAGNAME STREAM $2" ;;
esac
exit 0
STUB
printf '#!/bin/sh\nexit 0\n' > "$scratch/bin/curl"
chmod +x "$scratch/bin/"*
real_ssh=$(command -v ssh)
export PATH=$scratch/bin:$PATH TAGNAME=$tag

fails=0
passes=0
check() {
    local name=$1
    shift
    if "$@"; then
        echo "ok    $name"
        passes=$((passes + 1))
    else
        echo "FAIL  $name"
        echo "      the log's last 20 lines:"
        tail -n 20 "$LOG" | sed 's/^/        /'
        fails=$((fails + 1))
    fi
}
not() { ! "$@"; }
reached() { grep -q "^$1 $2" "$LOG"; }
await() {
    local _
    for _ in $(seq 1 150); do "$@" 2>/dev/null && return 0; sleep 0.1; done
    echo "FAIL  never reached: $*"
    exit 1
}
within() { # a bounded wait that is itself the verdict: fails rather than ends the run
    local _
    for _ in $(seq 1 150); do "$@" 2>/dev/null && return 0; sleep 0.1; done
    return 1
}
install() { # call-id host: one install in the background, in a session of its own, its output in out.<id>
    local id=$1 host=$2
    # shellcheck disable=SC2016 # the inner shell expands its own arguments
    (cd "$scratch/co" && exec setsid bash -c 'echo $$ > "$1"; env CALL="$2" tools/kiosk-install.sh "$3" "$4" > "$5" 2>&1; echo $? > "$6"' \
        _ "$scratch/pg.$id" "$id" "$host" "$scratch/bundle.raucb" "$scratch/out.$id" "$scratch/rc.$id") &
    disown
    await test -s "$scratch/pg.$id"
}
one="root@board-one-$tag.invalid"
two="root@board-two-$tag.invalid"
alias1="root@alias-one-$tag.invalid"
third="root@third-one-$tag.invalid"
rcof() { cat "$scratch/rc.$1" 2>/dev/null; }
refused_call() { # id host [VAR=value...]: a call that must be refused, bounded, its output in out.<id>
    local id=$1 host=$2
    shift 2
    (cd "$scratch/co" && env CALL="$id" "$@" timeout 5 tools/kiosk-install.sh "$host" "$scratch/bundle.raucb" > "$scratch/out.$id" 2>&1
        echo $? > "$scratch/rc.$id")
}
refused_by() { # id: refused with exit 1 and a message naming its holder
    [ "$(rcof "$1")" = 1 ] && grep -q "another install holds" "$scratch/out.$1" && return 0
    echo "      expected status 1 and a message naming the holder, measured status '$(rcof "$1")': $(cat "$scratch/out.$1" 2>/dev/null)"
    return 1
}

# Phase A. Phases A to E are one scenario on call 1's held lock; the sections after it each start their own. A second call to one board is refused, names the holder, and reached nothing but `ssh -G`
rm -f "$RELEASE" "$STATE/installed"
install 1 "$one"
await reached 1 "docker run"
refused_call 2 "$one"
first_pid=$(pgrep -P "$(cat "$scratch/pg.1")" | head -n 1)
refused() { refused_by 2 && grep -q "another install holds $one (pid and checkout: $first_pid $scratch/co)" "$scratch/out.2"; }
check "a second call is refused and names the holder" refused
only_g() { ! grep "^$1 " "$LOG" | grep -v ' ssh -G' | grep -q .; }
check "the refused call reached nothing but ssh -G" only_g 2
# Phase B: a call to another board goes on, and a call with another XDG_RUNTIME_DIR to the first board is refused
install 3 "$two"
check "another board goes on" within reached 3 "docker run"
mkdir -p "$scratch/xdg"
refused_call 4 "$one" XDG_RUNTIME_DIR="$scratch/xdg"
check "other environments meet on one lock" refused_by 4
check "that call reached nothing but ssh -G" only_g 4
# Phase C: two names for one address meet; a name that does not resolve is keyed as typed
refused_call 5 "$alias1"
check "a name that ssh -G maps to the board's own meets its lock" refused_by 5
check "that call reached nothing but ssh -G" only_g 5
refused_call 6 "$third"
check "a name that only getent maps to the board's address meets its lock" refused_by 6
check "that call reached nothing but ssh -G" only_g 6
# Phase D: a name that does not resolve is keyed as typed, user stripped: two users on it meet
install 7 "root@nores-$tag.invalid"
await reached 7 "docker run"
refused_call 8 "admin@nores-$tag.invalid"
check "a name that does not resolve is keyed with the user stripped" refused_by 8
check "that call reached nothing but ssh -G" only_g 8
# Phase E: the holder is released and ends normally, and nothing of it is left
touch "$RELEASE"
await test -e "$scratch/rc.1"
check "the first call ends normally" test "$(rcof 1)" = 0
await test -e "$scratch/rc.3"
await test -e "$scratch/rc.7"
none_alive() {
    local p
    [ -s "$STATE/streams.1" ] || return 1
    while read -r p; do
        ! kill -0 "$p" 2>/dev/null || return 1
    done < "$STATE/streams.1"
}
check "after the script ends none of its streaming ssh is left" none_alive

# free after one killed whole
rm -f "$RELEASE" "$STATE/installed"; : > "$LOG"
install 9 "$one"
await reached 9 "docker run"
kill -9 -- "-$(cat "$scratch/pg.9")" 2>/dev/null
await not kill -0 -- "-$(cat "$scratch/pg.9")"
install 10 "$one"
check "the lock is free after the first ended and after one killed whole" within reached 10 "docker run"
kill -9 -- "-$(cat "$scratch/pg.10")" 2>/dev/null
await not kill -0 -- "-$(cat "$scratch/pg.10")"

# a script killed alone frees the lock at once, though its streaming ssh live on: the next call goes
: > "$LOG"; rm -f "$RELEASE" "$STATE/installed"
install 11 "$one"
await reached 11 "docker run"
await reached 11 "ssh .*rauc install"
await reached 11 "ssh .*dmesg -w"
script=$(pgrep -P "$(cat "$scratch/pg.11")" | head -n 1)
await test -n "$script"
kill -9 "$script" 2>/dev/null
await not kill -0 "$script"
streams_alive() {
    local p
    [ -s "$STATE/streams.11" ] || return 1
    while read -r p; do
        kill -0 "$p" 2>/dev/null || return 1
    done < "$STATE/streams.11"
}
check "the streaming ssh of the killed script are still alive" streams_alive
install 12 "$one"
check "a script killed alone frees the lock though its streaming ssh live on" within reached 12 "docker run"

# Bundle server: a stale server is removed and a live one is kept; the port is read from a two-line `docker port`
: > "$LOG"; rm -f "$RELEASE" "$STATE/installed"
sleep 0 &
dead_pid=$!
wait "$dead_pid"
printf 'livecid %s\ndeadcid %s\n' "$$" "$dead_pid" > "$STATE/ps.list"
printf '0.0.0.0:5555\n[::]:5555\n' > "$STATE/port.out"
install 13 "root@board-six-$tag.invalid"
await reached 13 "docker run"
only_dead_removed() {
    reached 13 "docker rm -f deadcid" && ! reached 13 "docker rm -f livecid"
}
check "a server whose pid is dead is removed and one whose pid is alive is kept" only_dead_removed
port_read() { grep -q "serving .* at http://local:5555/bundle.raucb" "$scratch/out.13"; }
check "the port is the one on a two-line docker port" within port_read
rm -f "$STATE/ps.list" "$STATE/port.out"
touch "$RELEASE"
await test -e "$scratch/rc.13"

# The real ssh closes a descriptor it inherits, which the stub ssh's `exec 8>&-` stands in for
has_child() { pgrep -P "$1" > /dev/null; }
ssh_closes_fd8() {
    local p fd
    [ -n "$real_ssh" ] || { echo "      no ssh on PATH: not probed"; return 1; }
    (exec 8>> "$scratch/fd8"; exec "$real_ssh" -F /dev/null -o BatchMode=yes -o ProxyCommand='sleep 3' x.invalid) > /dev/null 2>&1 &
    p=$!
    await has_child "$p"
    [ "$(cat "/proc/$p/comm" 2>/dev/null)" = ssh ] || { echo "      the probed process is not ssh: not probed"; kill "$p" 2>/dev/null; return 1; }
    [ -d "/proc/$p/fd" ] || { echo "      no /proc/$p/fd: not probed"; kill "$p" 2>/dev/null; return 1; }
    for fd in /proc/$p/fd/*; do
        if [ "$(readlink "$fd")" = "$scratch/fd8" ]; then
            echo "      ssh still holds the inherited file on fd ${fd##*/}"
            kill "$p" 2>/dev/null
            return 1
        fi
    done
    kill "$p" 2>/dev/null
    wait "$p" 2>/dev/null
    return 0
}
check "the real ssh closes a descriptor it inherits" ssh_closes_fd8

echo "kiosk-install lock: $passes case(s) passed, $fails failed"
[ "$fails" -eq 0 ]
