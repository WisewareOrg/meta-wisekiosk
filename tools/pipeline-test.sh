#!/usr/bin/env bash
# Self-test for resolve-role.py, report.py's redact-and-cap, and the pre-post identity check.
#
#   tools/pipeline-test.sh
#
# resolve-role.py is the pipeline's own safety control. It must refuse every
# role but `bench` and take no address argument -- a wrong answer here is a
# script that could OTA or reboot the wall-mounted prod board unattended.
#
# Fixtures use RFC 5737 documentation addresses, never a real LAN address.
#
# The MAC/IPv4 used to prove redaction are split across variables so the
# literal never appears in this file's tracked text.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RESOLVE_ROLE="$HERE/pipeline/resolve-role.py"
REPORT="$HERE/pipeline/report.py"

# Unset an inherited GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR
# before using git below.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR 2>/dev/null || true

# Prefer the repo .venv's python3 if present.
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
# Internal locals avoid out/err/rc so callers' locals of those names are not
# shadowed.
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

# utf8_len TEXT -- character length as report.py's own --limit computes it
# (Python len() on UTF-8-decoded text), unlike bash's byte-counting ${#}.
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
# A. tools/pipeline/resolve-role.py
# =========================================================================

test_resolve_role() {
    local out err rc

    # Precondition: fails clearly if resolve-role.py is missing rather than
    # passing by coincidence.
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
    case "$out$err" in
        *"$PROD_ADDR"*)
            bad "resolve-role prod: the prod address appears in neither stdout nor stderr" \
                "out=$out err=$err" ;;
        *) ok "resolve-role prod: the prod address appears in neither stdout nor stderr" ;;
    esac

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ -n "$err" ]; then
        ok "resolve-role no-arg: refused, rc 2, nothing on stdout, reason on stderr"
    else
        bad "resolve-role no-arg: refused, rc 2, nothing on stdout, reason on stderr" \
            "rc=$rc out=$out err=$err"
    fi
    case "$out$err" in
        *"$PROD_ADDR"*)
            bad "resolve-role no-arg: the prod address appears in neither stdout nor stderr" \
                "out=$out err=$err" ;;
        *) ok "resolve-role no-arg: the prod address appears in neither stdout nor stderr" ;;
    esac

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$GOODMAP" swampland
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ -n "$err" ]; then
        ok "resolve-role unknown role: refused, rc 2, nothing on stdout, reason on stderr"
    else
        bad "resolve-role unknown role: refused, rc 2, nothing on stdout, reason on stderr" \
            "rc=$rc out=$out err=$err"
    fi
    case "$out$err" in
        *"$PROD_ADDR"*)
            bad "resolve-role unknown role: the prod address appears in neither stdout nor stderr" \
                "out=$out err=$err" ;;
        *) ok "resolve-role unknown role: the prod address appears in neither stdout nor stderr" ;;
    esac

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$NOBENCHMAP" bench
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ -n "$err" ]; then
        ok "resolve-role bench, map with no bench key: refused, rc 2"
    else
        bad "resolve-role bench, map with no bench key: refused, rc 2" \
            "rc=$rc out=$out err=$err"
    fi
    case "$out$err" in
        *"$PROD_ADDR"*)
            bad "resolve-role bench, map with no bench key: the prod address appears in neither stdout nor stderr" \
                "out=$out err=$err" ;;
        *) ok "resolve-role bench, map with no bench key: the prod address appears in neither stdout nor stderr" ;;
    esac

    capture out err rc "$PY" "$RESOLVE_ROLE" --map "$GOODMAP" bench extra
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ -n "$err" ]; then
        ok "resolve-role bench, extra positional: refused, rc 2, reason on stderr (no address argument)"
    else
        bad "resolve-role bench, extra positional: refused, rc 2, reason on stderr (no address argument)" \
            "rc=$rc out=$out err=$err"
    fi
    case "$out$err" in
        *"$PROD_ADDR"*)
            bad "resolve-role bench, extra positional: the prod address appears in neither stdout nor stderr" \
                "out=$out err=$err" ;;
        *) ok "resolve-role bench, extra positional: the prod address appears in neither stdout nor stderr" ;;
    esac

    # --map defaults to <repo root>/local/device-identity.md. Proven against
    # a fresh, throwaway git repository, never this checkout's own
    # local/device-identity.md.
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
# B. tools/pipeline/report.py build
# =========================================================================

test_report_build() {
    local out err rc

    # Precondition: fails clearly if report.py is missing rather than
    # passing by coincidence.
    if [ ! -f "$REPORT" ]; then
        bad "report.py exists" "not found at $REPORT"
        return
    fi

    # --- B1/B2: happy path, plus both redaction halves in one body --------
    # Every map value -> <role.key>; then an IPv4/MAC/hostname-shaped token
    # -> <redacted>.
    mkdir -p "$TOP/b1"
    printf 'VERDICT pr-run sha=deadbeef01 -> success (bench)\n' > "$TOP/b1/verdict.txt"
    printf 'diff --git a/kiosk-zero-w.yaml b/kiosk-zero-w.yaml\n' \
        > "$TOP/b1/delta.txt"
    printf 'stray leak check: bench=%s mac=%s ip=%s\n' \
        "$BENCH_ADDR" "$STRAY_MAC" "$STRAY_IP" >> "$TOP/b1/delta.txt"
    printf 'FOO := bar\n' >> "$TOP/b1/delta.txt"
    # Nested under a synthetic result_id, matching oeqa's real testresults.json
    # shape (sources/poky/meta/lib/oeqa/core/runner.py).
    cat > "$TOP/b1/results.json" <<'EOF'
{"runtime_kiosk-zero-w_raspberrypi0-wifi_20260930101500": {"configuration": {}, "result": {
  "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"},
  "wisekiosk.WiseKioskTest.test_healthz_within_bound": {"status": "PASSED"}
}}}
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
    # load_map_rows drops any key under PUBLIC_NS. A non-public value in the
    # same body confirms the exclusion is per-row.
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
    printf '{"runtime_kiosk-zero-w_raspberrypi0-wifi_20260930101500": {"configuration": {}, "result": {}}}\n' \
        > "$TOP/b2b/results.json"

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

    # --- B4: cap step 1 -- truncate a --log file from its head, keeping the
    # tail, at a line boundary. ----------------------------------------------
    mkdir -p "$TOP/b4"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b4/verdict.txt"
    printf 'diff --git a/x b/x\n+ok\n' > "$TOP/b4/delta.txt"
    cat > "$TOP/b4/results.json" <<'EOF'
{"runtime_kiosk-zero-w_raspberrypi0-wifi_20260930101500": {"configuration": {}, "result": {
  "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"}
}}}
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
    if [ "$(utf8_len "$out")" -le 4000 ]; then
        ok "report build, capped log: body is within --limit"
    else
        bad "report build, capped log: body is within --limit" "len=$(utf8_len "$out")"
    fi

    # --- B5: cap step 2 -- once --log is exhausted, strip `log` fields from
    # --results (case identity/status stay). --------------------------------
    mkdir -p "$TOP/b5"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b5/verdict.txt"
    printf 'diff --git a/x b/x\n+ok\n' > "$TOP/b5/delta.txt"
    "$PY" - <<PYEOF > "$TOP/b5/results.json"
import json
biglog = "RESULTLOGDETAIL-B5-PAYLOAD " * 150
data = {"runtime_kiosk-zero-w_raspberrypi0-wifi_20260930101500": {"configuration": {}, "result": {
    "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"},
    "wisekiosk.WiseKioskTest.test_render_large_log": {"status": "FAILED", "log": biglog},
}}}
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
    if [ "$(utf8_len "$out")" -le 1000 ]; then
        ok "report build, log-stripped: body is within --limit"
    else
        bad "report build, log-stripped: body is within --limit" "len=$(utf8_len "$out")"
    fi

    # --- B5b: cap order -- log truncation exhausts before results-log
    # stripping starts. mid_len is the body's size once --log's lines are
    # fully popped, with the results log field still intact. ----------------
    mkdir -p "$TOP/b5b"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b5b/verdict.txt"
    printf 'diff --git a/x b/x\n+ok\n' > "$TOP/b5b/delta.txt"
    # Not nested under a result_id like the fixtures above -- see commit message.
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

    # Measured from a raw file: command substitution strips trailing
    # newlines and would shift this boundary.
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

    # --- B5c: cap order extends to the delta -- once log truncation and
    # results-log stripping are exhausted, overflow truncates the delta: a
    # summary derived from the delta's own diff headers and +/- lines, the
    # delta's first 200 lines, then a truncation note. floor_len is the
    # body's size with log and results already minimal and the delta still
    # whole. ------------------------------------------------------------
    mkdir -p "$TOP/b5c"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b5c/verdict.txt"
    # 2000 files x 15 lines (5 metadata + 5 "-old" + 5 "+new") = 30 000 lines.
    # files=2000, plus=10000, minus=10000 -- computed the same way report.py's
    # delta_summary() does (count `^diff --git `, `^+` not `^++`, `^-` not `^--`).
    "$PY" -c '
for i in range(2000):
    print(f"diff --git a/file{i:04d}.yaml b/file{i:04d}.yaml")
    print("index 1111111..2222222 100644")
    print(f"--- a/file{i:04d}.yaml")
    print(f"+++ b/file{i:04d}.yaml")
    print("@@ -1,5 +1,5 @@")
    for j in range(5):
        print(f"-old line {j} of file {i:04d}, padded so truncation has bytes to cut")
    for j in range(5):
        print(f"+new line {j} of file {i:04d}, padded so truncation has bytes to cut")
' > "$TOP/b5c/delta.txt"
    DELTA_SUMMARY="2000 files changed, +10000/$(printf '\xe2\x88\x92')10000"
    "$PY" - <<PYEOF > "$TOP/b5c/results.json"
import json
biglog = "DELTAORDER-B5C-PAYLOAD " * 100
data = {"configuration": {}, "result": {
    "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"},
    "wisekiosk.WiseKioskTest.test_render_large_log": {"status": "FAILED", "log": biglog},
}}
print(json.dumps(data))
PYEOF
    "$PY" - <<PYEOF > "$TOP/b5c/results-stripped.json"
import json
data = {"configuration": {}, "result": {
    "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"},
    "wisekiosk.WiseKioskTest.test_render_large_log": {"status": "FAILED"},
}}
print(json.dumps(data))
PYEOF
    : > "$TOP/b5c/log.txt"
    i=1
    while [ "$i" -le 50 ]; do
        printf 'DELTAORDERLOG %04d of a small log, padded so truncation has bytes to cut xxxx\n' \
            "$i" >> "$TOP/b5c/log.txt"
        i=$((i + 1))
    done
    : > "$TOP/b5c/log-empty.txt"

    # Measured with log and results already minimal, delta still whole. The
    # limit must clear the ~1.5 MB delta or this call truncates it first.
    local floor_len
    "$PY" "$REPORT" build --map "$GOODMAP" --limit 10000000 \
        --verdict "$TOP/b5c/verdict.txt" --delta "$TOP/b5c/delta.txt" \
        --results "$TOP/b5c/results-stripped.json" \
        --log "deltaorderlog=$TOP/b5c/log-empty.txt" \
        > "$TOP/b5c/floor.out"
    floor_len=$("$PY" -c \
        'import sys; sys.stdout.write(str(len(open(sys.argv[1], encoding="utf-8").read())))' \
        "$TOP/b5c/floor.out")

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit "$floor_len" \
        --verdict "$TOP/b5c/verdict.txt" --delta "$TOP/b5c/delta.txt" \
        --results "$TOP/b5c/results.json" --log "deltaorderlog=$TOP/b5c/log.txt"
    if [ "$rc" -eq 0 ]; then
        ok "report build, cap order at the delta-untouched size: exits 0"
    else
        bad "report build, cap order at the delta-untouched size: exits 0" "rc=$rc err=$err"
    fi
    case "$out" in
        *"DELTAORDERLOG "*)
            bad "report build, cap order at the delta-untouched size: the log is fully truncated" "out=$out" ;;
        *) ok "report build, cap order at the delta-untouched size: the log is fully truncated" ;;
    esac
    case "$out" in
        *"DELTAORDER-B5C-PAYLOAD"*)
            bad "report build, cap order at the delta-untouched size: the results log field is stripped" "out=$out" ;;
        *) ok "report build, cap order at the delta-untouched size: the results log field is stripped" ;;
    esac
    case "$out" in
        *"file1999"*)
            ok "report build, cap order at the delta-untouched size: the delta is still whole" ;;
        *) bad "report build, cap order at the delta-untouched size: the delta is still whole" "out=$out" ;;
    esac
    case "$out" in
        *"delta truncated"*)
            bad "report build, cap order at the delta-untouched size: no truncation note yet" "out=$out" ;;
        *) ok "report build, cap order at the delta-untouched size: no truncation note yet" ;;
    esac

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit "$((floor_len - 1))" \
        --verdict "$TOP/b5c/verdict.txt" --delta "$TOP/b5c/delta.txt" \
        --results "$TOP/b5c/results.json" --log "deltaorderlog=$TOP/b5c/log.txt"
    if [ "$rc" -eq 0 ]; then
        ok "report build, cap order one byte tighter than the delta: exits 0"
    else
        bad "report build, cap order one byte tighter than the delta: exits 0" "rc=$rc err=$err"
    fi
    case "$out" in
        *"VERDICT pr-run -> success"*)
            ok "report build, cap order one byte tighter than the delta: the verdict is intact" ;;
        *) bad "report build, cap order one byte tighter than the delta: the verdict is intact" "out=$out" ;;
    esac
    case "$out" in
        *"delta truncated; full delta in the run dir"*)
            ok "report build, cap order one byte tighter than the delta: the truncation note is present" ;;
        *) bad "report build, cap order one byte tighter than the delta: the truncation note is present" \
            "out=$out" ;;
    esac
    case "$out" in
        *"$DELTA_SUMMARY"*)
            ok "report build, cap order one byte tighter than the delta: the derived summary line is present" ;;
        *) bad "report build, cap order one byte tighter than the delta: the derived summary line is present" \
            "out=$out" ;;
    esac
    case "$out" in
        *"file1999"*)
            bad "report build, cap order one byte tighter than the delta: the delta's tail is gone" "out=$out" ;;
        *) ok "report build, cap order one byte tighter than the delta: the delta's tail is gone" ;;
    esac
    case "$out" in
        *"file0000"*)
            ok "report build, cap order one byte tighter than the delta: the delta's head survives" ;;
        *) bad "report build, cap order one byte tighter than the delta: the delta's head survives" "out=$out" ;;
    esac
    if [ "$(utf8_len "$out")" -le "$((floor_len - 1))" ]; then
        ok "report build, cap order one byte tighter than the delta: body is within --limit"
    else
        bad "report build, cap order one byte tighter than the delta: body is within --limit" \
            "len=$(utf8_len "$out")"
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
# C. tools/pipeline/report.py check -- the pre-post gate
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
