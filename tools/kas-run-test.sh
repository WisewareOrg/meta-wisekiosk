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
# Cases: two builds never overlap; a waiter names the holder; a killed holder frees the lock; an
# interactive `shell` does not take it and `shell -c` does; a nested call is refused with exit 2; a
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
now() { date +%s.%N; }

# 1. two builds never overlap, and the waiter names the holder
: > "$log"
(cd "$scratch/one" && TAG=A HOLD=2 tools/kas-run.sh build a.yaml > "$scratch/a.out" 2>&1) &
sleep 0.5
(cd "$scratch/two" && TAG=B tools/kas-run.sh build b.yaml > "$scratch/b.out" 2>&1)
wait
[ "$(tr '\n' ' ' < "$log")" = "begin A end A begin B end B " ]
check "builds never overlap" $?
grep -q "waiting for another kas build on this host: [0-9]* $scratch/one" "$scratch/b.out"
check "the waiter names the holder's pid and checkout" $?

# 2. a killed holder frees the lock
: > "$log"
# its own process group, killed whole: the lock is held by every process that inherited it
(cd "$scratch/one" && TAG=A HOLD=30 exec setsid tools/kas-run.sh build a.yaml > /dev/null 2>&1) &
holder=$!
sleep 0.5
start=$(now)
(sleep 1; kill -9 -- "-$holder" 2>/dev/null || kill -9 "$holder") &
(cd "$scratch/two" && TAG=B tools/kas-run.sh build b.yaml > "$scratch/b2.out" 2>&1)
waited=$(echo "$(now) - $start" | bc)
[ "$(echo "$waited < 10" | bc)" -eq 1 ] && grep -q '^end B$' "$log"
check "a killed holder frees the lock" $?
wait 2>/dev/null

# 3. interactive shell does not take it and does not wait; shell -c does
: > "$log"
(cd "$scratch/one" && TAG=A HOLD=3 tools/kas-run.sh build a.yaml > /dev/null 2>&1) &
sleep 0.5
start=$(now)
(cd "$scratch/two" && TAG=S tools/kas-run.sh shell s.yaml > /dev/null 2>&1)
waited=$(echo "$(now) - $start" | bc)
[ "$(echo "$waited < 1.5" | bc)" -eq 1 ]
check "interactive shell does not wait" $?
start=$(now)
(cd "$scratch/two" && TAG=C tools/kas-run.sh shell s.yaml -c "bitbake x" > /dev/null 2>&1)
waited=$(echo "$(now) - $start" | bc)
[ "$(echo "$waited > 1.5" | bc)" -eq 1 ]
check "shell -c takes the lock" $?
wait

# 4. a nested call is refused with exit 2
: > "$log"; rm -f "$log.nested"
(cd "$scratch/one" && NEST="$scratch/one/tools/kas-run.sh" TAG=A tools/kas-run.sh build a.yaml > /dev/null 2>&1)
[ "$(tail -n 1 "$log.nested")" = "2" ] && grep -q 'nested' "$log.nested"
check "nested call refused with exit 2" $?

# 5. a lock that cannot be opened is an error naming the path
rm -f "$hs/kas-build.lock"
chmod 555 "$hs"
out=$(cd "$scratch/one" && tools/kas-run.sh build a.yaml 2>&1)
rc=$?
chmod 755 "$hs"
[ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'kas-build.lock'
check "an unopenable lock is an error that names the path" $?

# 6. a refused call does not wait for a held lock
: > "$log"
(cd "$scratch/one" && TAG=A HOLD=3 tools/kas-run.sh build a.yaml > /dev/null 2>&1) &
sleep 0.5
start=$(now)
(cd "$scratch/two" && tools/kas-run.sh build x.yaml --runtime-args y > /dev/null 2>&1)
rc=$?
waited=$(echo "$(now) - $start" | bc)
[ "$rc" -eq 2 ] && [ "$(echo "$waited < 1.5" | bc)" -eq 1 ]
check "a refusal does not wait" $?
wait

echo "kas-run lock: $fails case(s) failed"
[ "$fails" -eq 0 ]
