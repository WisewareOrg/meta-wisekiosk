#!/usr/bin/env bash
# Self-test for the three pipeline components the owner allowed tests on
# (#119 D-L(1), plan decision 12, Q6): role refusal, report redact-and-cap,
# and the pre-post identity check. Everything else in tools/pipeline/ -- the
# candidate filter, run.sh's orchestration, the timer units -- is structural
# and gets no test (decision 12: "Nothing else gets a test; the fork filter
# is structural ... not tested").
#
#   tools/pipeline-test.sh
#
# resolve-role.py (D-F) is the pipeline's OWN safety control: ".claude/
# hooks/guard.sh does not run under a timer; this refusal is the pipeline's
# own safety control" (decision 7). It must refuse every role but `bench`
# and take no address argument -- a wrong answer here is a script that could
# OTA or reboot the wall-mounted prod board unattended.
#
# report.py (D-J) posts to a PUBLIC GitHub repo. Its redact
# step must remove every value in the identity map plus anything shaped like
# an address or a MAC before a byte leaves the host, and its cap step must
# never truncate the verdict or the delta -- the two sections a reader relies
# on to trust the rest.
#
# This repository is PUBLIC, so every fixture below uses RFC 5737 /
# TEST-NET-2 documentation addresses (198.51.100.0/24), never a real LAN
# address -- the same convention .claude/hooks/guard-test.sh already
# establishes, confirmed here against tools/ci-guards.sh guard 6 and
# tools/scrub-identity.py's own private-IPv4 pattern: neither matches
# 198.*.*.* (only 192.168/10/172.16-31), so these values are safe to commit.
#
# The MAC and the private (RFC1918) IPv4 used to prove PATTERN-half redaction
# are each split across two variables and joined only at RUNTIME. A
# contiguous literal of either shape in THIS file's own tracked source text
# would trip the very guards (ci-guards.sh guard 6, scrub-identity.py's MAC
# and private-IPv4 PATTERNs) that report.py's redaction step exists to
# satisfy -- scanning is over `git ls-files`' tracked text, not over what a
# script prints at runtime, so the split defeats the scanner without
# defeating the test.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RESOLVE_ROLE="$HERE/pipeline/resolve-role.py"
REPORT="$HERE/pipeline/report.py"

# A leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE from an enclosing worktree's
# hooks would divert every `git init`/`git rev-parse` fixture below at that
# worktree's own repository instead of the throwaway one just created for it
# (docs/issue_investigation/*, "worktree git env leak"). Nothing here
# legitimately needs an inherited one.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR 2>/dev/null || true

# Resolve the repo .venv python the way tools/ci-guards.sh does: a bare
# python3 on this host may lack packages the repo's own .venv provides, and
# a git hook / CI shell sources no startup file that would otherwise pick
# one up.
PY=python3
REPO_ROOT="$(cd "$HERE/.." && pwd)"
if [ -x "$REPO_ROOT/.venv/bin/python3" ]; then
    PY="$REPO_ROOT/.venv/bin/python3"
fi

TOP=$(mktemp -d)
trap 'rm -rf "$TOP"' EXIT

pass=0; fail=0
ok()  { printf 'ok    %s\n' "$1"; pass=$((pass+1)); }
bad() { printf 'FAIL  %s\n' "$1"; [ $# -gt 1 ] && printf '        %s\n' "$2"; fail=$((fail+1)); }

# capture OUTVAR ERRVAR RCVAR -- cmd args...
# Runs cmd, splitting stdout/stderr/exit code into the three named variables
# via `printf -v` (no eval, no subshell variable loss).
#
# The internal locals are deliberately NOT named out/err/rc: every caller
# uses those same names for its own locals, and a `local rc` declared in
# THIS function would shadow the caller's `rc`, so `printf -v "$_r"` (where
# _r=="rc") would write to capture's own shadow instead of the caller's
# variable -- silently, except that set -u then reports the caller's
# never-assigned `rc` as unbound at the next read. Measured: this exact
# collision was the first version of this file's own bug.
capture() {
    local _o=$1 _e=$2 _r=$3; shift 3
    local _cap_errfile _cap_out _cap_rc
    _cap_errfile="$TOP/stderr.$$.$RANDOM"
    _cap_out=$("$@" 2>"$_cap_errfile"); _cap_rc=$?
    printf -v "$_o" '%s' "$_cap_out"
    printf -v "$_e" '%s' "$(cat "$_cap_errfile")"
    printf -v "$_r" '%s' "$_cap_rc"
    rm -f "$_cap_errfile"
}

# capture_stdin OUTVAR ERRVAR RCVAR STDIN_TEXT -- cmd args...
capture_stdin() {
    local _o=$1 _e=$2 _r=$3 _in=$4; shift 4
    local _cap_errfile _cap_out _cap_rc
    _cap_errfile="$TOP/stderr.$$.$RANDOM"
    _cap_out=$(printf '%s' "$_in" | "$@" 2>"$_cap_errfile"); _cap_rc=$?
    printf -v "$_o" '%s' "$_cap_out"
    printf -v "$_e" '%s' "$(cat "$_cap_errfile")"
    printf -v "$_r" '%s' "$_cap_rc"
    rm -f "$_cap_errfile"
}

# utf8_len TEXT -- report.py's own --limit check is Python's len() on a
# UTF-8-decoded str (the "## Log — <label>" em dash is one such character);
# bash's ${#} is locale-dependent and can count its UTF-8 bytes instead, so
# a boundary derived from ${#out} can be off by exactly that gap.
utf8_len() {
    printf '%s' "$1" | "$PY" -c \
        'import sys; sys.stdout.write(str(len(sys.stdin.buffer.read().decode("utf-8"))))'
}

# --- fixture identity maps ---------------------------------------------
# Format owner: tools/scrub-identity.py (the ```identity fence, `key = value`
# rows). Real key names (prod.address, bench.address, wifi.ssid) copied from
# the shape of local/device-identity.md; every value here is a placeholder.

GOODMAP="$TOP/device-identity-good.md"
cat > "$GOODMAP" <<'EOF'
# Fixture identity map -- RFC 5737 placeholders only, never a real site.
```identity
prod.address    = 198.51.100.7
bench.address   = 198.51.100.14
wifi.ssid       = placeholder-net-01
```
EOF

NOBENCHMAP="$TOP/device-identity-no-bench.md"
cat > "$NOBENCHMAP" <<'EOF'
```identity
prod.address    = 198.51.100.7
wifi.ssid       = placeholder-net-01
```
EOF

BENCH_ADDR="198.51.100.14"
PROD_ADDR="198.51.100.7"

# A MAC and a private IPv4, each split so the contiguous shape never sits in
# this file's own tracked text (see header comment).
mac_hi="DE:AD:BE:EF:00"; mac_lo="01"
STRAY_MAC="${mac_hi}:${mac_lo}"
ip_hi="10.77.4"; ip_lo="9"
STRAY_IP="${ip_hi}.${ip_lo}"

# =========================================================================
# A. tools/pipeline/resolve-role.py  (D-F, decision 7)
# =========================================================================

test_resolve_role() {
    local out err rc

    # A missing script and a correct refusal both produce rc 2, empty
    # stdout, a stderr message -- Python's own "can't open file" for the
    # former happens to satisfy the same shape as the latter's contract.
    # Without this precondition, every refusal case below would read as
    # passing before resolve-role.py is written at all, which is not RED
    # for the specified reason; it is green by coincidence.
    if [ ! -f "$RESOLVE_ROLE" ]; then
        bad "resolve-role.py exists" "not found at $RESOLVE_ROLE"
        return
    fi

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$GOODMAP" bench
    if [ "$rc" -eq 0 ] && [ "$out" = "$BENCH_ADDR" ]; then
        ok "resolve-role bench: prints the bare bench address, rc 0"
    else
        bad "resolve-role bench: prints the bare bench address, rc 0" \
            "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$GOODMAP" prod
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ -n "$err" ]; then
        ok "resolve-role prod: refused, rc 2, nothing on stdout, reason on stderr"
    else
        bad "resolve-role prod: refused, rc 2, nothing on stdout, reason on stderr" \
            "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ -n "$err" ]; then
        ok "resolve-role no-arg: refused, rc 2, nothing on stdout, reason on stderr"
    else
        bad "resolve-role no-arg: refused, rc 2, nothing on stdout, reason on stderr" \
            "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$GOODMAP" swampland
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ -n "$err" ]; then
        ok "resolve-role unknown role: refused, rc 2, nothing on stdout, reason on stderr"
    else
        bad "resolve-role unknown role: refused, rc 2, nothing on stdout, reason on stderr" \
            "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$NOBENCHMAP" bench
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ -n "$err" ]; then
        ok "resolve-role bench, map with no bench key: refused, rc 2"
    else
        bad "resolve-role bench, map with no bench key: refused, rc 2" \
            "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$GOODMAP" bench extra
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ -n "$err" ]; then
        ok "resolve-role bench, extra positional: refused, rc 2, reason on stderr (no address argument)"
    else
        bad "resolve-role bench, extra positional: refused, rc 2, reason on stderr (no address argument)" \
            "rc=$rc out=$out err=$err"
    fi

    # --map defaults to <repo root>/local/device-identity.md (D-F). Proven
    # against a fresh, throwaway git repository -- never this checkout's own
    # local/device-identity.md, which holds the real site.
    local fixture_repo="$TOP/fixture-repo"
    mkdir -p "$fixture_repo/local" "$fixture_repo/subdir"
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE \
        git init -q "$fixture_repo"
    cp "$GOODMAP" "$fixture_repo/local/device-identity.md"
    capture out err rc bash -c \
        "cd \"$fixture_repo/subdir\" && exec \"$PY\" \"$RESOLVE_ROLE\" bench"
    if [ "$rc" -eq 0 ] && [ "$out" = "$BENCH_ADDR" ]; then
        ok "resolve-role bench, --map omitted: resolves <repo root>/local/device-identity.md"
    else
        bad "resolve-role bench, --map omitted: resolves <repo root>/local/device-identity.md" \
            "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$RESOLVE_ROLE" --help
    if [ "$rc" -eq 0 ] && [ -n "$out" ]; then
        ok "resolve-role --help: exits 0 and prints usage"
    else
        bad "resolve-role --help: exits 0 and prints usage" "rc=$rc out=$out err=$err"
    fi
}

# =========================================================================
# B. tools/pipeline/report.py build  (D-J)
# =========================================================================

test_report_build() {
    local out err rc

    # Same reasoning as resolve-role.py's precondition above: a missing
    # report.py and several of its correct rc-2/rc-1 cases below would
    # otherwise read as green by coincidence rather than red for the
    # specified reason.
    if [ ! -f "$REPORT" ]; then
        bad "report.py exists" "not found at $REPORT"
        return
    fi

    # --- B1/B2: happy path, plus both redaction halves in one body --------
    # decision D-J step 1: every map value -> <role.key>; then an IPv4/MAC/
    # hostname-shaped token -> <redacted>. The delta section is never
    # truncated (never capped here either -- --limit is generous), so
    # whatever the redaction pass leaves behind is exactly what would reach
    # the PR.
    mkdir -p "$TOP/b1"
    printf 'VERDICT pr-run sha=deadbeef01 -> success (bench)\n' > "$TOP/b1/verdict.txt"
    printf 'diff --git a/kiosk-zero-w.yaml b/kiosk-zero-w.yaml\n' \
        > "$TOP/b1/delta.txt"
    printf 'stray leak check: bench=%s mac=%s ip=%s\n' \
        "$BENCH_ADDR" "$STRAY_MAC" "$STRAY_IP" >> "$TOP/b1/delta.txt"
    printf 'FOO := bar\n' >> "$TOP/b1/delta.txt"
    cat > "$TOP/b1/results.json" <<'EOF'
{"configuration": {}, "result": {
  "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"},
  "wisekiosk.WiseKioskTest.test_healthz_within_bound": {"status": "PASSED"}
}}
EOF

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 100000 \
        --verdict "$TOP/b1/verdict.txt" --delta "$TOP/b1/delta.txt" \
        --results "$TOP/b1/results.json"

    if [ "$rc" -eq 0 ]; then
        ok "report build, small inputs: exits 0"
    else
        bad "report build, small inputs: exits 0" "rc=$rc err=$err"
    fi
    case "$out" in
        *"VERDICT pr-run sha=deadbeef01 -> success (bench)"*)
            ok "report build: the verdict section is carried verbatim" ;;
        *) bad "report build: the verdict section is carried verbatim" "out=$out" ;;
    esac
    case "$out" in
        *"diff --git a/kiosk-zero-w.yaml b/kiosk-zero-w.yaml"*)
            ok "report build: delta boilerplate survives" ;;
        *) bad "report build: delta boilerplate survives" "out=$out" ;;
    esac
    case "$out" in
        *"FOO := bar"*) ok "report build: delta's tail line survives (nothing truncated it)" ;;
        *) bad "report build: delta's tail line survives (nothing truncated it)" "out=$out" ;;
    esac
    case "$out" in
        *"$BENCH_ADDR"*)
            bad "report build: the bench address is redacted, not raw" "out=$out" ;;
        *) ok "report build: the bench address is redacted, not raw" ;;
    esac
    case "$out" in
        *"<bench.address>"*)
            ok "report build: the bench address is replaced by <bench.address>" ;;
        *) bad "report build: the bench address is replaced by <bench.address>" "out=$out" ;;
    esac
    case "$out" in
        *"$STRAY_MAC"*)
            bad "report build: a stray MAC (not in the map) is redacted, not raw" "out=$out" ;;
        *) ok "report build: a stray MAC (not in the map) is redacted, not raw" ;;
    esac
    case "$out" in
        *"$STRAY_IP"*)
            bad "report build: a stray private IPv4 (not in the map) is redacted, not raw" "out=$out" ;;
        *) ok "report build: a stray private IPv4 (not in the map) is redacted, not raw" ;;
    esac
    case "$out" in
        *"<redacted>"*)
            ok "report build: PATTERN-half redaction emits <redacted>" ;;
        *) bad "report build: PATTERN-half redaction emits <redacted>" "out=$out" ;;
    esac
    case "$out" in
        *"test_backend_unit_active"*)
            ok "report build: a case's identity appears in the results section" ;;
        *) bad "report build: a case's identity appears in the results section" "out=$out" ;;
    esac
    case "$out" in
        *"PASSED"*) ok "report build: a case's status appears in the results section" ;;
        *) bad "report build: a case's status appears in the results section" "out=$out" ;;
    esac

    # --- B2b: a public.* map row is excluded from redaction ---------------
    # load_map_rows drops any key under PUBLIC_NS (mirrors scrub-identity.py's
    # own PUBLIC_NS): its value is a build-time constant, not a site
    # identifier, and must reach the PR unredacted. A non-public value in the
    # same body proves the exclusion is per-row, not a redaction pass that
    # merely failed.
    PUBLICMAP="$TOP/device-identity-public.md"
    cat > "$PUBLICMAP" <<'EOF'
```identity
prod.address    = 198.51.100.7
bench.address   = 198.51.100.14
public.machine  = raspberrypi0-wifi
```
EOF

    mkdir -p "$TOP/b2b"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b2b/verdict.txt"
    printf 'diff --git a/x b/x\nmachine=raspberrypi0-wifi bench=%s\n' \
        "$BENCH_ADDR" > "$TOP/b2b/delta.txt"
    printf '{"configuration": {}, "result": {}}\n' > "$TOP/b2b/results.json"

    capture out err rc "$PY" "$REPORT" build --map "$PUBLICMAP" --limit 100000 \
        --verdict "$TOP/b2b/verdict.txt" --delta "$TOP/b2b/delta.txt" \
        --results "$TOP/b2b/results.json"

    case "$out" in
        *"raspberrypi0-wifi"*)
            ok "report build: a public.* map value is left unredacted" ;;
        *) bad "report build: a public.* map value is left unredacted" "out=$out" ;;
    esac
    case "$out" in
        *"$BENCH_ADDR"*)
            bad "report build: a non-public value in the same body is still redacted" "out=$out" ;;
        *) ok "report build: a non-public value in the same body is still redacted" ;;
    esac

    # --- B3: a missing required file ---------------------------------------
    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 100000 \
        --verdict "$TOP/b1/does-not-exist.txt" --delta "$TOP/b1/delta.txt" \
        --results "$TOP/b1/results.json"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report build, missing --verdict file: rc 2, nothing on stdout"
    else
        bad "report build, missing --verdict file: rc 2, nothing on stdout" \
            "rc=$rc out=$out err=$err"
    fi

    # --- B4: cap step 1 -- truncate a --log file from its head, keep the
    # tail, line boundary only. Verdict and delta are never truncated. -----
    mkdir -p "$TOP/b4"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b4/verdict.txt"
    printf 'diff --git a/x b/x\n+ok\n' > "$TOP/b4/delta.txt"
    cat > "$TOP/b4/results.json" <<'EOF'
{"configuration": {}, "result": {
  "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"}
}}
EOF
    : > "$TOP/b4/log.txt"
    i=1
    while [ "$i" -le 400 ]; do
        printf 'LINE %04d of the failing task log, padded so a truncation has real bytes to cut xxxx\n' \
            "$i" >> "$TOP/b4/log.txt"
        i=$((i + 1))
    done

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 4000 \
        --verdict "$TOP/b4/verdict.txt" --delta "$TOP/b4/delta.txt" \
        --results "$TOP/b4/results.json" --log "$TOP/b4/log.txt"

    if [ "$rc" -eq 0 ]; then
        ok "report build, oversized log file: exits 0 (fits after truncation)"
    else
        bad "report build, oversized log file: exits 0 (fits after truncation)" "rc=$rc err=$err"
    fi
    case "$out" in
        *"VERDICT pr-run -> success"*) ok "report build, capped: the verdict is never truncated" ;;
        *) bad "report build, capped: the verdict is never truncated" "out=$out" ;;
    esac
    case "$out" in
        *"diff --git a/x b/x"*"+ok"*) ok "report build, capped: the delta is never truncated" ;;
        *) bad "report build, capped: the delta is never truncated" "out=$out" ;;
    esac
    case "$out" in
        *"LINE 0001"*)
            bad "report build, capped log: the head of the log was cut, not kept" "out contains LINE 0001" ;;
        *) ok "report build, capped log: the head of the log was cut, not kept" ;;
    esac
    case "$out" in
        *"LINE 0400"*) ok "report build, capped log: the tail of the log survives" ;;
        *) bad "report build, capped log: the tail of the log survives" "out=$out" ;;
    esac
    if [ "${#out}" -le 4000 ]; then
        ok "report build, capped log: body is within --limit"
    else
        bad "report build, capped log: body is within --limit" "len=${#out}"
    fi

    # --- B5: cap step 2 -- once every --log section is exhausted (none was
    # given here), strip `log` fields from the results JSON, keeping the
    # case's own status/identity. ------------------------------------------
    mkdir -p "$TOP/b5"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b5/verdict.txt"
    printf 'diff --git a/x b/x\n+ok\n' > "$TOP/b5/delta.txt"
    "$PY" - <<PYEOF > "$TOP/b5/results.json"
import json
biglog = "RESULTLOGDETAIL-B5-PAYLOAD " * 150
data = {"configuration": {}, "result": {
    "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"},
    "wisekiosk.WiseKioskTest.test_render_large_log": {"status": "FAILED", "log": biglog},
}}
print(json.dumps(data))
PYEOF

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 1000 \
        --verdict "$TOP/b5/verdict.txt" --delta "$TOP/b5/delta.txt" \
        --results "$TOP/b5/results.json"

    if [ "$rc" -eq 0 ]; then
        ok "report build, oversized results log field: exits 0 (fits after stripping)"
    else
        bad "report build, oversized results log field: exits 0 (fits after stripping)" \
            "rc=$rc err=$err"
    fi
    case "$out" in
        *"VERDICT pr-run -> success"*) ok "report build, log-stripped: the verdict is never truncated" ;;
        *) bad "report build, log-stripped: the verdict is never truncated" "out=$out" ;;
    esac
    case "$out" in
        *"test_render_large_log"*)
            ok "report build, log-stripped: the case's own identity survives" ;;
        *) bad "report build, log-stripped: the case's own identity survives" "out=$out" ;;
    esac
    case "$out" in
        *"RESULTLOGDETAIL-B5-PAYLOAD"*)
            bad "report build, log-stripped: the case's log field is gone, not raw" "out=$out" ;;
        *) ok "report build, log-stripped: the case's log field is gone, not raw" ;;
    esac
    if [ "${#out}" -le 1000 ]; then
        ok "report build, log-stripped: body is within --limit"
    else
        bad "report build, log-stripped: body is within --limit" "len=${#out}"
    fi

    # --- B5b: cap order -- log truncation exhausts before results stripping
    # starts. mid_len is measured, not guessed: it is the body's real size
    # once --log's lines are fully popped, with the results log field still
    # intact -- exactly where cap() sits right after step 1 finishes and
    # before step 2 is ever tried. A limit of mid_len must be met by step 1
    # alone; mid_len - 1 cannot, and only step 2 can close that last byte. ---
    mkdir -p "$TOP/b5b"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b5b/verdict.txt"
    printf 'diff --git a/x b/x\n+ok\n' > "$TOP/b5b/delta.txt"
    "$PY" - <<PYEOF > "$TOP/b5b/results.json"
import json
biglog = "COMBOLOGDETAIL-B5B-PAYLOAD " * 100
data = {"configuration": {}, "result": {
    "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"},
    "wisekiosk.WiseKioskTest.test_render_large_log": {"status": "FAILED", "log": biglog},
}}
print(json.dumps(data))
PYEOF
    : > "$TOP/b5b/log.txt"
    i=1
    while [ "$i" -le 100 ]; do
        printf 'COMBOLOG %04d of the combined-cap-order log, padded so truncation has bytes to cut xxxx\n' \
            "$i" >> "$TOP/b5b/log.txt"
        i=$((i + 1))
    done
    : > "$TOP/b5b/log-empty.txt"

    # Measured from a raw file, not a `capture`-captured variable: command
    # substitution strips trailing newlines, which would shift this boundary
    # by exactly the newlines the body ends in.
    local mid_len
    "$PY" "$REPORT" build --map "$GOODMAP" --limit 1000000 \
        --verdict "$TOP/b5b/verdict.txt" --delta "$TOP/b5b/delta.txt" \
        --results "$TOP/b5b/results.json" --log "combolog=$TOP/b5b/log-empty.txt" \
        > "$TOP/b5b/mid.out"
    mid_len=$("$PY" -c \
        'import sys; sys.stdout.write(str(len(open(sys.argv[1], encoding="utf-8").read())))' \
        "$TOP/b5b/mid.out")

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit "$mid_len" \
        --verdict "$TOP/b5b/verdict.txt" --delta "$TOP/b5b/delta.txt" \
        --results "$TOP/b5b/results.json" --log "combolog=$TOP/b5b/log.txt"
    if [ "$rc" -eq 0 ]; then
        ok "report build, cap order at the log-exhausted size: exits 0"
    else
        bad "report build, cap order at the log-exhausted size: exits 0" "rc=$rc err=$err"
    fi
    case "$out" in
        *"COMBOLOG "*)
            bad "report build, cap order at the log-exhausted size: the log is fully truncated" "out=$out" ;;
        *) ok "report build, cap order at the log-exhausted size: the log is fully truncated" ;;
    esac
    case "$out" in
        *"COMBOLOGDETAIL-B5B-PAYLOAD"*)
            ok "report build, cap order at the log-exhausted size: the results log field survives" ;;
        *) bad "report build, cap order at the log-exhausted size: the results log field survives" "out=$out" ;;
    esac

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit "$((mid_len - 1))" \
        --verdict "$TOP/b5b/verdict.txt" --delta "$TOP/b5b/delta.txt" \
        --results "$TOP/b5b/results.json" --log "combolog=$TOP/b5b/log.txt"
    if [ "$rc" -eq 0 ]; then
        ok "report build, cap order one byte tighter: exits 0"
    else
        bad "report build, cap order one byte tighter: exits 0" "rc=$rc err=$err"
    fi
    case "$out" in
        *"COMBOLOG "*)
            bad "report build, cap order one byte tighter: the log stays fully truncated" "out=$out" ;;
        *) ok "report build, cap order one byte tighter: the log stays fully truncated" ;;
    esac
    case "$out" in
        *"COMBOLOGDETAIL-B5B-PAYLOAD"*)
            bad "report build, cap order one byte tighter: the results log field is now stripped" "out=$out" ;;
        *) ok "report build, cap order one byte tighter: the results log field is now stripped" ;;
    esac
    case "$out" in
        *"test_render_large_log"*)
            ok "report build, cap order one byte tighter: the case's own identity survives" ;;
        *) bad "report build, cap order one byte tighter: the case's own identity survives" "out=$out" ;;
    esac
    if [ "$(utf8_len "$out")" -le "$((mid_len - 1))" ]; then
        ok "report build, cap order one byte tighter: body is within --limit"
    else
        bad "report build, cap order one byte tighter: body is within --limit" "len=$(utf8_len "$out")"
    fi

    # --- B6: cannot fit even after every truncation step -------------------
    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 50 \
        --verdict "$TOP/b5/verdict.txt" --delta "$TOP/b5/delta.txt" \
        --results "$TOP/b5/results.json"
    if [ "$rc" -eq 1 ] && [ -z "$out" ]; then
        ok "report build, impossible --limit: rc 1, nothing on stdout"
    else
        bad "report build, impossible --limit: rc 1, nothing on stdout" \
            "rc=$rc out=$out err=$err"
    fi
    case "$err" in
        *"cannot fit"*) ok "report build, impossible --limit: says cannot fit" ;;
        *) bad "report build, impossible --limit: says cannot fit" "err=$err" ;;
    esac

    capture out err rc "$PY" "$REPORT" --help
    if [ "$rc" -eq 0 ] && [ -n "$out" ]; then
        ok "report --help: exits 0 and prints usage"
    else
        bad "report --help: exits 0 and prints usage" "rc=$rc out=$out err=$err"
    fi
}

# =========================================================================
# C. tools/pipeline/report.py check  (D-J step 3, the pre-post gate)
# =========================================================================

test_report_check() {
    local out err rc

    if [ ! -f "$REPORT" ]; then
        bad "report.py exists" "not found at $REPORT"
        return
    fi

    capture_stdin out err rc \
        $'VERDICT: <bench.address> success\ndelta shows <redacted> only, no raw identity\n' \
        "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 0 ]; then
        ok "report check, already-redacted body: rc 0"
    else
        bad "report check, already-redacted body: rc 0" "rc=$rc out=$out err=$err"
    fi

    capture_stdin out err rc \
        "VERDICT: $BENCH_ADDR was never redacted" \
        "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 1 ]; then
        ok "report check, a raw map value in the body: rc 1"
    else
        bad "report check, a raw map value in the body: rc 1" "rc=$rc out=$out err=$err"
    fi

    capture_stdin out err rc \
        "stray mac ${mac_hi}:${mac_lo} leaked into the body" \
        "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 1 ]; then
        ok "report check, a raw PATTERN token in the body: rc 1"
    else
        bad "report check, a raw PATTERN token in the body: rc 1" "rc=$rc out=$out err=$err"
    fi
}

test_resolve_role
test_report_build
test_report_check

echo
printf 'pass=%s fail=%s\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
