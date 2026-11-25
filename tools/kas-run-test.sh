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
# Exit: 0 every case passed; 1 a case failed.
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
sleep "${HOLD:-0}"
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
check() { # name, condition result (0 pass)
    if [ "$2" -eq 0 ]; then echo "ok    $1"; else echo "FAIL  $1"; fails=$((fails + 1)); fi
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
hold() { # start a build in checkout one that holds the lock for $1 s, in the background
    (cd "$scratch/one" && TAG=A HOLD="$1" tools/kas-run.sh build a.yaml > /dev/null 2>&1) &
    until has "begin A"; do sleep 0.1; done
}

# 1. two builds never overlap, and the waiter names the holder
: > "$log"
(cd "$scratch/one" && TAG=A HOLD=2 tools/kas-run.sh build a.yaml > "$scratch/a.out" 2>&1) &
until has "begin A"; do sleep 0.1; done
(cd "$scratch/two" && TAG=B tools/kas-run.sh build b.yaml > "$scratch/b.out" 2>&1)
wait
[ "$(tr '\n' ' ' < "$log")" = "begin A end A begin B end B " ]
check "builds never overlap" $?
grep -q "waiting for another kas build on this host: [0-9]* $scratch/one" "$scratch/b.out"
check "the waiter names the holder's pid and checkout" $?

# 2. a killed holder frees the lock: its own process group, killed whole, as every process that
# inherited the descriptor holds the lock
: > "$log"
(cd "$scratch/one" && TAG=A HOLD=30 exec setsid tools/kas-run.sh build a.yaml > /dev/null 2>&1) &
holder=$!
until has "begin A"; do sleep 0.1; done
(sleep 1; kill -9 -- "-$holder" 2>/dev/null || kill -9 "$holder") &
(cd "$scratch/two" && TAG=B timeout 15 tools/kas-run.sh build b.yaml > /dev/null 2>&1)
has "end B"
check "a killed holder frees the lock" $?
wait 2>/dev/null

# 3. the exit status is kas-container's
(cd "$scratch/one" && EXITS=7 tools/kas-run.sh build a.yaml > /dev/null 2>&1)
[ "$?" -eq 7 ]
check "the exit status is kas-container's" $?

# 4. an interactive shell does not take the lock; shell with -c, --cmd or --command does
: > "$log"
hold 3
(cd "$scratch/two" && TAG=S tools/kas-run.sh shell s.yaml > /dev/null 2>&1)
has "end S" && ! has "end A"
check "interactive shell does not wait" $?
wait
for flag in -c --cmd --command; do
    : > "$log"
    hold 2
    (cd "$scratch/two" && TAG=C timeout 15 tools/kas-run.sh shell s.yaml "$flag" "bitbake x" > /dev/null 2>&1)
    before "end A" "begin C"
    check "shell $flag takes the lock" $?
    wait
done

# 5. a nested call is refused with exit 2
: > "$log"; rm -f "$log.nested"
(cd "$scratch/one" && NEST="$scratch/one/tools/kas-run.sh" TAG=A tools/kas-run.sh build a.yaml > /dev/null 2>&1)
[ "$(tail -n 1 "$log.nested")" = "2" ] && grep -q 'nested' "$log.nested"
check "nested call refused with exit 2" $?

# 6. a lock that cannot be opened is an error naming the path
rm -f "$hs/kas-build.lock"
chmod 555 "$hs"
out=$(cd "$scratch/one" && tools/kas-run.sh build a.yaml 2>&1)
rc=$?
chmod 755 "$hs"
[ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'kas-build.lock'
check "an unopenable lock is an error that names the path" $?

# 7. a refused call does not wait for a held lock
: > "$log"
hold 3
(cd "$scratch/two" && tools/kas-run.sh build x.yaml --runtime-args y > /dev/null 2>&1)
rc=$?
! has "end A"
refused_early=$?
[ "$rc" -eq 2 ] && [ "$refused_early" -eq 0 ]
check "a refusal does not wait" $?
wait

# 8. the waiter's exit status is kas-container's too
: > "$log"
hold 2
(cd "$scratch/two" && EXITS=9 TAG=B timeout 15 tools/kas-run.sh build b.yaml > /dev/null 2>&1)
[ "$?" -eq 9 ]
check "the waiter's exit status is kas-container's" $?
wait

# 9. two waiters both name the holder, and both run after it
: > "$log"
mkdir -p "$scratch/three/tools"
cp "$scratch/two/tools/"* "$scratch/three/tools/"
hold 3
(cd "$scratch/two" && TAG=B tools/kas-run.sh build b.yaml > "$scratch/w2.out" 2>&1) &
(cd "$scratch/three" && TAG=C tools/kas-run.sh build c.yaml > "$scratch/w3.out" 2>&1) &
wait
n=$(grep -l "waiting for another kas build on this host: [0-9]* $scratch/one" "$scratch/w2.out" "$scratch/w3.out" | wc -l)
[ "$n" -eq 2 ] && before "end A" "begin B" && before "end A" "begin C" && has "end B" && has "end C"
check "two waiters both name the holder and both run after it" $?

# 10. an interrupted waiter never runs kas-container
: > "$log"
hold 3
(cd "$scratch/two" && TAG=B timeout -s INT 1 tools/kas-run.sh build b.yaml > /dev/null 2>&1)
! has "begin B"
check "an interrupted waiter never builds" $?
wait

echo "kas-run lock: $fails case(s) failed"
[ "$fails" -eq 0 ]
