#!/usr/bin/env bash
# Self-test for the build lock in tools/kas-run.sh.
#
#   tools/kas-run-test.sh
#
# Runs the SHIPPED script (or the one named by KAS_RUN_UNDER_TEST) from two scratch checkouts, with
# HOME in a scratch directory and a stub `kas-container` first on PATH that records when it begins
# and ends and sleeps. The real build-input writers are replaced by stubs; nothing touches the
# host's hashserv directory, Docker or a real build.
#
# Cases are judged by the order of begin and end lines in one log, never by elapsed time. They are:
# two builds never overlap; a waiter names the holder; a killed holder frees the lock; the exit status
# is kas-container's; an interactive `shell` does not take it and `shell -c`, `--cmd` and `--command` do; a nested call is refused with exit 2; a
# lock that cannot be opened is an error that names its path; a refused call does not wait.
#
# TO WATCH THIS FAIL -- before trusting a green run, run it against a scratch copy of the script,
# one seed each, with KAS_RUN_UNDER_TEST=<copy>:
#   * delete the two `flock` words in the lock block: "builds never overlap"
#   * delete `export KAS_RUN_LOCKED=1`: "nested call refused"
#   * make the lock block run for every verb: "interactive shell does not wait"
#   * move the lock block above the --runtime-args refusal: "refusal does not wait"
#
# Exit: 0 every case passed; 1 a case failed, or the script or stub never started.
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
shipped=${KAS_RUN_UNDER_TEST:-$root/tools/kas-run.sh}
scratch=$(mktemp -d)
trap 'jobs -p | xargs -r kill 2>/dev/null; rm -rf "$scratch"' EXIT

export HOME=$scratch/home
hs=$HOME/.local/share/bitbake-hashserv
mkdir -p "$hs" "$scratch/bin"
log=$scratch/log
export LOG=$log

cat > "$scratch/bin/kas-container" <<'STUB'
#!/bin/bash
echo "begin ${TAG:-?}" >> "$LOG"
# held until the test releases it, or for HOLD seconds
if [ -n "${RELEASE:-}" ]; then
    for _ in $(seq 1 600); do [ -e "$RELEASE" ] && break; sleep 0.1; done
else
    sleep "${HOLD:-0}"
fi
if [ -n "${NEST:-}" ]; then timeout -s KILL 10 "$NEST" build nested.yaml > "$LOG.nested" 2>&1; echo "$?" >> "$LOG.nested"; fi
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
    if "$@"; then echo "ok    $name"; else echo "FAIL  $name"; fails=$((fails + 1)); fi
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
    (cd "$scratch/one" && RELEASE="$release" TAG=A tools/kas-run.sh build a.yaml > /dev/null 2>&1) &
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
(cd "$scratch/one" && RELEASE="$release" TAG=A exec setsid tools/kas-run.sh build a.yaml > /dev/null 2>&1) &
holder=$!
await "begin A"
(sleep 1; kill -9 -- "-$holder" 2>/dev/null || kill -9 "$holder") &
(cd "$scratch/two" && TAG=B timeout 15 tools/kas-run.sh build b.yaml > /dev/null 2>&1)
check "a killed holder frees the lock" has "end B"
wait 2>/dev/null

# 3. the exit status is kas-container's
(cd "$scratch/one" && EXITS=7 tools/kas-run.sh build a.yaml > /dev/null 2>&1)
status=$?
check "the exit status is kas-container's" test "$status" -eq 7

# 4. an interactive shell does not take the lock; shell with -c, --cmd or --command does
: > "$log"
hold
(cd "$scratch/two" && TAG=S tools/kas-run.sh shell s.yaml > /dev/null 2>&1)
ran_beside_holder() { has "end S" && not has "end A"; }
check "interactive shell does not wait" ran_beside_holder
let_go
for flag in -c --cmd --command; do
    : > "$log"
    hold
    (cd "$scratch/two" && TAG=C timeout 30 tools/kas-run.sh shell s.yaml "$flag" "bitbake x" > /dev/null 2>&1) &
    sleep 1
    ! has "begin C"
    held=$?
    let_go
    waited_for_holder() { [ "$held" -eq 0 ] && before "end A" "begin C"; }
    check "shell $flag takes the lock" waited_for_holder
done

# 5. a nested call is refused with exit 2
: > "$log"; rm -f "$log.nested"
(cd "$scratch/one" && NEST="$scratch/one/tools/kas-run.sh" TAG=A tools/kas-run.sh build a.yaml > /dev/null 2>&1)
nested_refused() { [ "$(tail -n 1 "$log.nested")" = "2" ] && grep -q 'nested' "$log.nested"; }
check "nested call refused with exit 2" nested_refused

# 6. a lock that cannot be opened is an error naming the path
rm -f "$hs/kas-build.lock"
chmod 555 "$hs"
out=$(cd "$scratch/one" && tools/kas-run.sh build a.yaml 2>&1)
rc=$?
chmod 755 "$hs"
names_the_path() { [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'kas-build.lock'; }
check "an unopenable lock is an error that names the path" names_the_path

# 7. a refused call does not wait for a held lock
: > "$log"
hold
(cd "$scratch/two" && tools/kas-run.sh build x.yaml --runtime-args y > /dev/null 2>&1)
rc=$?
! has "end A"
refused_early=$?
let_go
refused_at_once() { [ "$rc" -eq 2 ] && [ "$refused_early" -eq 0 ]; }
check "a refusal does not wait" refused_at_once

# 8. the waiter's exit status is kas-container's too
: > "$log"
hold
(cd "$scratch/two" && EXITS=9 TAG=B timeout 30 tools/kas-run.sh build b.yaml > /dev/null 2>&1; echo "$?" > "$scratch/rc8") &
sleep 1
let_go
check "the waiter's exit status is kas-container's" test "$(cat "$scratch/rc8")" -eq 9

# 9. two waiters both name the holder, and both run after it
: > "$log"
mkdir -p "$scratch/three/tools"
cp "$scratch/two/tools/"* "$scratch/three/tools/"
hold
(cd "$scratch/two" && TAG=B timeout 30 tools/kas-run.sh build b.yaml > "$scratch/w2.out" 2>&1) &
(cd "$scratch/three" && TAG=C timeout 30 tools/kas-run.sh build c.yaml > "$scratch/w3.out" 2>&1) &
sleep 1
let_go
n=$(grep -l "waiting for another kas build on this host: [0-9]* $scratch/one" "$scratch/w2.out" "$scratch/w3.out" | wc -l)
both_wait_and_run() { [ "$n" -eq 2 ] && before "end A" "begin B" && before "end A" "begin C" && has "end B" && has "end C"; }
check "two waiters both name the holder and both run after it" both_wait_and_run

# 10. an interrupted waiter never runs kas-container (TERM: a caller without job control ignores INT)
: > "$log"
hold
(cd "$scratch/two" && TAG=B timeout -s TERM 1 tools/kas-run.sh build b.yaml > /dev/null 2>&1)
let_go
check "an interrupted waiter never builds" not has "begin B"

echo "kas-run lock: $fails case(s) failed"
[ "$fails" -eq 0 ]
