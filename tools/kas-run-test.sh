#!/usr/bin/env bash
# Self-test for tools/kas-run.sh: the build lock and the keys directory.
#
#   tools/kas-run-test.sh
#
# Runs the SHIPPED script (or the one named by KAS_RUN_UNDER_TEST) from scratch checkouts, with
# HOME in a scratch directory and a stub `kas-container` first on PATH that records when it begins
# and ends and sleeps. The real build-input writers are replaced by stubs; nothing touches the
# host's hashserv directory, Docker or a real build.
#
# Cases are judged by the order of begin and end lines in one log, never by elapsed time. They are:
# two builds never overlap; a waiter names the holder; a killed holder frees the lock; the exit status
# is kas-container's; only `shell` with at most one more argument does not take it, and
# `shell f -c x`, `shell f --command=x` and `shell f -kc x` do; a lock that cannot be opened stops the
# call before the container, with the script's own message naming its path; a refused call does not
# wait; two waiters both name the holder and both run after it; a waiter interrupted while it waits never
# builds; a keyed call makes local/keys as the caller, with the mount still read-only, and an unkeyed call
# makes nothing; a failed mkdir of local/keys stops before the container and names the path.
#
# On a failure the scratch directory is kept and named, each failed check prints what it ran and the log,
# and every call's output is printed.
#
# TO WATCH THIS FAIL -- before trusting a green run, run it against a scratch copy of the script,
# one seed each, with KAS_RUN_UNDER_TEST=<copy>:
#   * delete the `flock -n 9 || …` line in the lock block: "builds never overlap" and "two waiters both name
#     the holder and both run after it"
#   * drop `$(cat "$lock")` from the waiting message: "the waiter names the holder's pid and checkout"
#   * start `setsid sleep 30 &` after the lock is taken, so a process outside the caller's group keeps the
#     descriptor: the run stops at "never saw 'begin A'" (case 1's leaked holder outlasts it; case 2 owns the
#     killed holder)
#   * replace `exec kas-container …` with the same call followed by `|| true`: "the exit status is
#     kas-container's" and "the waiter's exit status is kas-container's"
#   * replace the lock's `|| { echo …; exit 1; }` with `|| true`: "an unopenable lock stops the call …"
#   * add `trap '' TERM` at the top: "a waiter interrupted while it waits never builds"
#   * read the shell case as `shell` with none of -c, --cmd or --command: "shell <config> --command=bitbake x takes the lock"
#   * make the lock block run for every verb: "interactive shell does not wait"
#   * move the lock block above the --runtime-args refusal: "refusal does not wait"
#   * delete `mkdir -p local/keys`: "a keyed call makes local/keys"
#   * move that mkdir out of the PIPELINE_KEYS_DIR block: "a call without PIPELINE_KEYS_DIR makes no local/"
#   * drop `:ro` from the keys mount: "the keys mount stays read-only"
#   * replace the mkdir's error with `|| true`: "a failed mkdir of local/keys stops before the container"
#
# Exit: 0 every case passed; 1 a case failed, the script or stub never started, or it was run as root,
# where the unwritable directories cases 5 and 11 make do not deny a write.
set -u

if [ "$(id -u)" -eq 0 ]; then
    echo "kas-run-test: cannot seed an unwritable directory as root (cases 5 and 11); run it as a normal user"
    exit 1
fi

root=$(cd "$(dirname "$0")/.." && pwd)
shipped=${KAS_RUN_UNDER_TEST:-$root/tools/kas-run.sh}
scratch=$(mktemp -d)
finish() {
    local rc=$? f
    jobs -p | xargs -r kill 2>/dev/null
    if [ "$rc" -eq 0 ]; then
        rm -rf "$scratch"
        return
    fi
    for f in "$scratch"/*.out; do
        [ -s "$f" ] && { echo "--- $f"; cat "$f"; }
    done
    echo "kas-run-test: scratch kept at $scratch"
}
trap finish EXIT

unset PIPELINE_KEYS_DIR KAS_RUN_TMP_DIR KAS_RUN_ENV
export HOME=$scratch/home
hs=$HOME/.local/share/bitbake-hashserv
mkdir -p "$hs" "$scratch/bin"
log=$scratch/log
export LOG=$log

cat > "$scratch/bin/kas-container" <<'STUB'
#!/bin/bash
echo "begin ${TAG:-?}" >> "$LOG"
echo "local=$([ -d local ] && echo yes || echo no) keys_owner=$(stat -c %u local/keys 2>/dev/null || echo none)" >> "$LOG.local"
echo "$*" >> "$LOG.args"
# held until the test releases it, or for HOLD seconds
if [ -n "${RELEASE:-}" ]; then
    for _ in $(seq 1 600); do [ -e "$RELEASE" ] && break; sleep 0.1; done
else
    sleep "${HOLD:-0}"
fi
echo "end ${TAG:-?}" >> "$LOG"
exit "${EXITS:-0}"
STUB
chmod +x "$scratch/bin/kas-container"
export PATH=$scratch/bin:$PATH

for c in one two; do
    mkdir -p "$scratch/$c/tools"
    cp "$shipped" "$scratch/$c/tools/kas-run.sh"
    printf '#!/bin/sh\nexit 0\n' > "$scratch/$c/tools/write-build-rev.sh"
    : > "$scratch/$c/tools/go-mods.py"
    : > "$scratch/$c/tools/app-lockfile.py"
    chmod +x "$scratch/$c/tools/"*.sh
done

fails=0
check() { # name, then the command that must succeed
    local name=$1
    shift
    if "$@"; then
        echo "ok    $name"
    else
        echo "FAIL  $name"
        echo "      ran: $*"
        sed 's/^/      log: /' "$log"
        fails=$((fails + 1))
    fi
}
not() { # the command must fail
    ! "$@"
}
log_is() { # the log holds exactly these words, in order
    [ "$(tr '\n' ' ' < "$log")" = "$*" ]
}
has() { # a line is in the log
    grep -qx "$1" "$log"
}
before() { # line $1 comes before line $2 in the log
    local a b
    a=$(grep -n -x -m1 "$1" "$log" | cut -d: -f1)
    b=$(grep -n -x -m1 "$2" "$log" | cut -d: -f1)
    [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ]
}
await() { # a line in the log, or a failure of the whole test if it never comes
    local n
    for n in $(seq 1 150); do
        has "$1" && return 0
        sleep 0.1
    done
    echo "FAIL  never saw '$1' in the log: the script did not start or the stub did not run"
    exit 1
}
release="$scratch/release"
hold() { # start a build in checkout one that holds the lock until $release exists
    rm -f "$release"
    (cd "$scratch/one" && RELEASE="$release" TAG=A tools/kas-run.sh build a.yaml > "$scratch/hold.out" 2>&1) &
    await "begin A"
}
let_go() { # release the holder and wait for everything started
    touch "$release"
    wait
}

# 1. two builds never overlap, and the waiter names the holder
: > "$log"
rm -f "$release"
(cd "$scratch/one" && RELEASE="$release" TAG=A tools/kas-run.sh build a.yaml > "$scratch/a.out" 2>&1) &
await "begin A"
(cd "$scratch/two" && TAG=B tools/kas-run.sh build b.yaml > "$scratch/b.out" 2>&1) &
for _ in $(seq 1 100); do grep -q waiting "$scratch/b.out" 2>/dev/null && break; sleep 0.1; done
let_go
check "builds never overlap" log_is "begin A end A begin B end B "
check "the waiter names the holder's pid and checkout" \
    grep -q "waiting for another kas build on this host: [0-9]* $scratch/one" "$scratch/b.out"

# 2. a killed holder frees the lock: its own process group, killed whole, as every process that
# inherited the descriptor holds the lock
: > "$log"
rm -f "$release"
(cd "$scratch/one" && RELEASE="$release" TAG=A exec setsid tools/kas-run.sh build a.yaml > "$scratch/2a.out" 2>&1) &
holder=$!
await "begin A"
(sleep 1; kill -9 -- "-$holder" 2>/dev/null || kill -9 "$holder") &
(cd "$scratch/two" && TAG=B timeout 15 tools/kas-run.sh build b.yaml > "$scratch/2b.out" 2>&1)
check "a killed holder frees the lock" has "end B"
wait 2>/dev/null

# 3. the exit status is kas-container's
(cd "$scratch/one" && EXITS=7 tools/kas-run.sh build a.yaml > "$scratch/3.out" 2>&1)
status=$?
check "the exit status is kas-container's" test "$status" -eq 7

# 4. an interactive shell does not take the lock; shell given a command, in any spelling, does
: > "$log"
hold
(cd "$scratch/two" && TAG=S tools/kas-run.sh shell s.yaml > "$scratch/4.out" 2>&1)
ran_beside_holder() { has "end S" && not has "end A"; }
check "interactive shell does not wait" ran_beside_holder
let_go
shell_waits() { # the shell call with these arguments waits for the holder
    : > "$log"
    hold
    (cd "$scratch/two" && TAG=C timeout 30 tools/kas-run.sh shell s.yaml "$@" > "$scratch/c.out" 2>&1) &
    local _
    for _ in $(seq 1 100); do grep -q "waiting for another kas build" "$scratch/c.out" 2>/dev/null && break; sleep 0.1; done
    ! has "begin C"
    held=$?
    let_go
    [ "$held" -eq 0 ] && before "end A" "begin C"
}
for words in "-c|bitbake x" "--command=bitbake x" "-kc|bitbake x"; do
    IFS='|' read -r -a args <<< "$words"
    check "shell <config> ${args[0]} takes the lock" shell_waits "${args[@]}"
done

# 5. a lock that cannot be opened stops the call before the container, with the script's own message
: > "$log"
rm -f "$hs/kas-build.lock"
chmod 555 "$hs"
(cd "$scratch/one" && TAG=L tools/kas-run.sh build a.yaml > "$scratch/5.out" 2>&1)
rc=$?
chmod 755 "$hs"
stops_naming_the_path() {
    [ "$rc" -eq 1 ] && grep -qF "tools/kas-run.sh: cannot open the build lock $hs/kas-build.lock" "$scratch/5.out" \
        && not has "begin L"
}
check "an unopenable lock stops the call before the container, and the script's message names the path" \
    stops_naming_the_path

# 6. a refused call does not wait for a held lock
: > "$log"
hold
(cd "$scratch/two" && tools/kas-run.sh build x.yaml --runtime-args y > "$scratch/6.out" 2>&1)
rc=$?
! has "end A"
refused_early=$?
let_go
refused_at_once() { [ "$rc" -eq 2 ] && [ "$refused_early" -eq 0 ]; }
check "a refusal does not wait" refused_at_once

# 7. the waiter's exit status is kas-container's too
: > "$log"
hold
(cd "$scratch/two" && EXITS=9 TAG=B timeout 30 tools/kas-run.sh build b.yaml > "$scratch/7.out" 2>&1; echo "$?" > "$scratch/rc7") &
sleep 1
let_go
check "the waiter's exit status is kas-container's" test "$(cat "$scratch/rc7")" -eq 9

# 8. two waiters both name the holder, and both run after it
: > "$log"
mkdir -p "$scratch/three/tools"
cp "$scratch/two/tools/"* "$scratch/three/tools/"
hold
(cd "$scratch/two" && HOLD=1 TAG=B timeout 30 tools/kas-run.sh build b.yaml > "$scratch/w2.out" 2>&1) &
(cd "$scratch/three" && HOLD=1 TAG=C timeout 30 tools/kas-run.sh build c.yaml > "$scratch/w3.out" 2>&1) &
for _ in $(seq 1 100); do
    [ "$(grep -l "waiting for another kas build" "$scratch/w2.out" "$scratch/w3.out" 2>/dev/null | wc -l)" -eq 2 ] && break
    sleep 0.1
done
let_go
n=$(grep -l "waiting for another kas build on this host: [0-9]* $scratch/one" "$scratch/w2.out" "$scratch/w3.out" | wc -l)
both_wait_and_run() {
    [ "$n" -eq 2 ] && { log_is "begin A end A begin B end B begin C end C " || log_is "begin A end A begin C end C begin B end B "; }
}
check "two waiters both name the holder and both run after it" both_wait_and_run

# 9. a waiter interrupted while it waits never runs kas-container (TERM: a caller without job control
# ignores INT)
: > "$log"
hold
(cd "$scratch/two" && TAG=B exec tools/kas-run.sh build b.yaml > "$scratch/9.out" 2>&1) &
waiter=$!
for _ in $(seq 1 100); do grep -q "waiting for another kas build" "$scratch/9.out" 2>/dev/null && break; sleep 0.1; done
grep -q "waiting for another kas build" "$scratch/9.out"
was_waiting=$?
kill -TERM "$waiter" 2>/dev/null
for _ in $(seq 1 50); do kill -0 "$waiter" 2>/dev/null || break; sleep 0.1; done
let_go
interrupted_never_built() { [ "$was_waiting" -eq 0 ] && not has "begin B"; }
check "a waiter interrupted while it waits never builds" interrupted_never_built

# 10. a keyed call makes local/keys, as the caller, before the container starts, and the keys mount stays
# read-only; a call without PIPELINE_KEYS_DIR makes nothing
for c in four five; do
    mkdir -p "$scratch/$c/tools"
    cp "$scratch/two/tools/"* "$scratch/$c/tools/"
done
mkdir -p "$scratch/keys-src"
rm -f "$log.local" "$log.args"
(cd "$scratch/four" && PIPELINE_KEYS_DIR="$scratch/keys-src" tools/kas-run.sh build k.yaml > "$scratch/10k.out" 2>&1)
check "a keyed call makes local/keys as the caller before the container starts" \
    grep -qx "local=yes keys_owner=$(id -u)" "$log.local"
check "the keys mount stays read-only" grep -q -- "-v $scratch/keys-src:/work/local/keys:ro" "$log.args"
rm -f "$log.local"
(cd "$scratch/five" && tools/kas-run.sh build n.yaml > "$scratch/10n.out" 2>&1)
check "a call without PIPELINE_KEYS_DIR makes no local/" grep -qx "local=no keys_owner=none" "$log.local"

# 11. a failed mkdir of local/keys stops before the container starts, and the error names the path
mkdir -p "$scratch/six/tools" "$scratch/six/local"
cp "$scratch/two/tools/"* "$scratch/six/tools/"
chmod 555 "$scratch/six/local"
rm -f "$log.local"
out=$(cd "$scratch/six" && PIPELINE_KEYS_DIR="$scratch/keys-src" tools/kas-run.sh build k.yaml 2>&1)
rc=$?
chmod 755 "$scratch/six/local"
stopped_early() { [ "$rc" -ne 0 ] && [ ! -e "$log.local" ] && printf '%s' "$out" | grep -q "$scratch/six/local/keys"; }
check "a failed mkdir of local/keys stops before the container and names the path" stopped_early

echo "kas-run: $fails case(s) failed"
[ "$fails" -eq 0 ]
