#!/usr/bin/env bash
# Self-test for report.py's redact-and-cap and the pre-post identity check.
#
#   tools/pipeline-test.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPORT="$HERE/pipeline/report.py"
RUNSH="$HERE/pipeline/run.sh"

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR 2>/dev/null || true

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

# capture OUTVAR ERRVAR RCVAR cmd args... -- sets each var to cmd's stdout, stderr, rc.
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

# capture_stdin OUTVAR ERRVAR RCVAR STDIN_TEXT cmd args...
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

utf8_len() {
    printf '%s' "$1" | "$PY" -c \
        'import sys; sys.stdout.write(str(len(sys.stdin.buffer.read().decode("utf-8"))))'
}

# file_len PATH -- a file's length read back as text ($(...) itself strips
# trailing newlines, which a raw byte count would not).
file_len() {
    "$PY" -c 'import sys; sys.stdout.write(str(len(open(sys.argv[1], encoding="utf-8").read())))' "$1"
}

# find_boundary PATTERN LO HI PROBE_FN -- binary search in [LO,HI] for the
# largest limit whose PROBE_FN output still matches PATTERN. Assumes
# monotonic: PATTERN present for every limit >= the boundary, absent below
# it (an empty/failed probe counts as absent). Prints the boundary.
find_boundary() {
    local pattern=$1 lo=$2 hi=$3 probe=$4
    while [ $((hi - lo)) -gt 1 ]; do
        local mid=$(( (lo + hi) / 2 )) out
        out=$("$probe" "$mid" 2>/dev/null)
        if printf '%s' "$out" | grep -q "$pattern"; then
            hi=$mid
        else
            lo=$mid
        fi
    done
    printf '%s' "$hi"
}

# --- fixture identity maps ---------------------------------------------
# Map format: local/device-identity.md §"Format".

GOODMAP="$TOP/device-identity-good.md"
cat > "$GOODMAP" <<'EOF'
# Fixture identity map -- RFC 5737 placeholders only.
```identity
prod.address    = 198.51.100.7
bench.address   = 198.51.100.14
wifi.ssid       = placeholder-net-01
```
EOF

BENCH_ADDR="198.51.100.14"

# Split: the joined literals trip gitleaks and tools/scrub-identity.py --check.
mac_hi="DE:AD:BE:EF:00"; mac_lo="01"
STRAY_MAC="${mac_hi}:${mac_lo}"
ip_hi="10.77.4"; ip_lo="9"
STRAY_IP="${ip_hi}.${ip_lo}"
pk_dash="-----"; pk_begin="BEGIN"; pk_priv="PRIVATE"; pk_key="KEY"
PK_HEADER="${pk_dash}${pk_begin} ${pk_priv} ${pk_key}${pk_dash}"
PK_HEADER_RSA="${pk_dash}${pk_begin} RSA ${pk_priv} ${pk_key}${pk_dash}"
PK_HEADER_OPENSSH="${pk_dash}${pk_begin} OPENSSH ${pk_priv} ${pk_key}${pk_dash}"
PK_FOOTER_OPENSSH="${pk_dash}END OPENSSH ${pk_priv} ${pk_key}${pk_dash}"

# =========================================================================
# A. tools/pipeline/report.py build
# =========================================================================

test_report_build() {
    local out err rc

    if [ ! -f "$REPORT" ]; then
        bad "report.py exists" "not found at $REPORT"
        return
    fi

    # --- happy path, both redaction halves ---
    mkdir -p "$TOP/b1"
    printf 'VERDICT pr-run sha=deadbeef01 -> success (bench)\n' > "$TOP/b1/verdict.txt"
    printf 'diff --git a/kiosk-zero-w.yaml b/kiosk-zero-w.yaml\n' \
        > "$TOP/b1/delta.txt"
    printf 'stray leak check: bench=%s mac=%s ip=%s\n' \
        "$BENCH_ADDR" "$STRAY_MAC" "$STRAY_IP" >> "$TOP/b1/delta.txt"
    printf 'FOO := bar\n' >> "$TOP/b1/delta.txt"
    # oeqa's testresults.json shape: sources/poky/meta/lib/oeqa/core/runner.py.
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
        *"FOO := bar"*) ok "report build: delta's tail line survives" ;;
        *) bad "report build: delta's tail line survives" "out=$out" ;;
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

    # --- a public.* map row is not redacted ---
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

    # --- the longest map value is replaced first ---
    PREFIXMAP="$TOP/device-identity-prefix.md"
    cat > "$PREFIXMAP" <<'EOF'
```identity
short.address   = 192.0.2.1
long.address    = 192.0.2.10
```
EOF

    mkdir -p "$TOP/b2c"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b2c/verdict.txt"
    printf 'diff --git a/x b/x\nlong host at 192.0.2.10\n' > "$TOP/b2c/delta.txt"
    printf '{"runtime_kiosk-zero-w_raspberrypi0-wifi_20260930101500": {"configuration": {}, "result": {}}}\n' \
        > "$TOP/b2c/results.json"

    capture out err rc "$PY" "$REPORT" build --map "$PREFIXMAP" --limit 100000 \
        --verdict "$TOP/b2c/verdict.txt" --delta "$TOP/b2c/delta.txt" \
        --results "$TOP/b2c/results.json"

    case "$out" in
        *"<long.address>"*)
            ok "report build: the longer prefix-sharing value is replaced by its own token intact" ;;
        *) bad "report build: the longer prefix-sharing value is replaced by its own token intact" "out=$out" ;;
    esac
    case "$out" in
        *"192.0.2.10"*)
            bad "report build: the longer prefix-sharing value is not left raw" "out=$out" ;;
        *) ok "report build: the longer prefix-sharing value is not left raw" ;;
    esac
    case "$out" in
        *"<short.address>"*)
            bad "report build: no fragment of the shorter value's token appears" "out=$out" ;;
        *) ok "report build: no fragment of the shorter value's token appears" ;;
    esac

    # --- map-value redaction is case-insensitive (the fixture SSID has
    # letters; the address does not, so it cannot exercise this) ---
    mkdir -p "$TOP/b2d"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b2d/verdict.txt"
    printf 'diff --git a/x b/x\nseen on %s\n' "$(printf '%s' 'placeholder-net-01' | tr '[:lower:]' '[:upper:]')" \
        > "$TOP/b2d/delta.txt"
    printf '{"configuration": {}, "result": {}}\n' > "$TOP/b2d/results.json"

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 100000 \
        --verdict "$TOP/b2d/verdict.txt" --delta "$TOP/b2d/delta.txt" \
        --results "$TOP/b2d/results.json"
    case "$out" in
        *"<wifi.ssid>"*)
            ok "report build: an uppercase map value is still redacted (case-insensitive)" ;;
        *) bad "report build: an uppercase map value is still redacted (case-insensitive)" "out=$out" ;;
    esac

    # --- a missing required file ---
    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 100000 \
        --verdict "$TOP/b1/does-not-exist.txt" --delta "$TOP/b1/delta.txt" \
        --results "$TOP/b1/results.json"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report build, missing --verdict file: rc 2, nothing on stdout"
    else
        bad "report build, missing --verdict file: rc 2, nothing on stdout" \
            "rc=$rc out=$out err=$err"
    fi

    # --- invalid UTF-8 in a raw input refuses rc 2, not a traceback ---
    mkdir -p "$TOP/b3"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b3/verdict.txt"
    printf 'diff --git a/x b/x\n+ok\n' > "$TOP/b3/delta.txt"
    printf '{"configuration": {}, "result": {}}\n' > "$TOP/b3/results.json"
    printf 'VERDICT pr-run -> success\xff\xfe\n' > "$TOP/b3/bad-verdict.txt"

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 100000 \
        --verdict "$TOP/b3/bad-verdict.txt" --delta "$TOP/b3/delta.txt" \
        --results "$TOP/b3/results.json"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report build, invalid UTF-8 in --verdict: rc 2, nothing on stdout"
    else
        bad "report build, invalid UTF-8 in --verdict: rc 2, nothing on stdout" \
            "rc=$rc out=$out err=$err"
    fi

    # --- a results file that is not a JSON object refuses rc 2 ---
    printf '[]' > "$TOP/b3/list-results.json"
    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 100000 \
        --verdict "$TOP/b3/verdict.txt" --delta "$TOP/b3/delta.txt" \
        --results "$TOP/b3/list-results.json"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report build, --results is a JSON array: rc 2, nothing on stdout"
    else
        bad "report build, --results is a JSON array: rc 2, nothing on stdout" \
            "rc=$rc out=$out err=$err"
    fi

    # --- a results case whose value is not a JSON object refuses rc 2 ---
    printf '{"configuration": {}, "result": {"case1": "FAILED"}}' > "$TOP/b3/string-case.json"
    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 100000 \
        --verdict "$TOP/b3/verdict.txt" --delta "$TOP/b3/delta.txt" \
        --results "$TOP/b3/string-case.json"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report build, a results case value is a string: rc 2, nothing on stdout"
    else
        bad "report build, a results case value is a string: rc 2, nothing on stdout" \
            "rc=$rc out=$out err=$err"
    fi

    # --- private key material in the raw input is refused, uncapped ---
    mkdir -p "$TOP/b6"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b6/verdict.txt"
    printf 'diff --git a/x b/x\n+ok\n' > "$TOP/b6/delta.txt"
    printf '{"configuration": {}, "result": {}}\n' > "$TOP/b6/results.json"
    {
        i=1
        while [ "$i" -le 5 ]; do
            printf 'preamble line %d, padded so a truncation has real bytes to cut xxxxxxxxxxx\n' "$i"
            i=$((i + 1))
        done
        printf -- '%s\n' "$PK_HEADER_OPENSSH"
        i=1
        while [ "$i" -le 20 ]; do
            printf 'QmFzZTY0bGluZSBvZiBmYWtlIG9wZW5zc2gga2V5IGRhdGEsIHBhZGRlZCBzbyBpdCBsb29rcyBy\n'
            i=$((i + 1))
        done
        printf -- '%s\n' "$PK_FOOTER_OPENSSH"
    } > "$TOP/b6/log.txt"

    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 100000 \
        --verdict "$TOP/b6/verdict.txt" --delta "$TOP/b6/delta.txt" \
        --results "$TOP/b6/results.json" --log "$TOP/b6/log.txt"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report build, private key in the raw log: refused rc 2, nothing on stdout"
    else
        bad "report build, private key in the raw log: refused rc 2, nothing on stdout" \
            "rc=$rc out=$out err=$err"
    fi

    # A --limit tight enough that head-truncation alone would have dropped
    # the preamble and the BEGIN line (the pre-fix defect: check ran only on
    # the already-capped body, so the key's body+END line passed as clean).
    # The uncapped scan in build must still catch it before any capping.
    capture out err rc "$PY" "$REPORT" build --map "$GOODMAP" --limit 400 \
        --verdict "$TOP/b6/verdict.txt" --delta "$TOP/b6/delta.txt" \
        --results "$TOP/b6/results.json" --log "$TOP/b6/log.txt"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report build, private key survives head-truncation: still refused rc 2 at a tight --limit"
    else
        bad "report build, private key survives head-truncation: still refused rc 2 at a tight --limit" \
            "rc=$rc out=$out err=$err"
    fi

    # --- cap step 1: --log truncated from its head, with a truncation note ---
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
        ok "report build, oversized log file: exits 0"
    else
        bad "report build, oversized log file: exits 0" "rc=$rc err=$err"
    fi
    case "$out" in
        *"VERDICT pr-run -> success"*) ok "report build, capped: the verdict is intact" ;;
        *) bad "report build, capped: the verdict is intact" "out=$out" ;;
    esac
    case "$out" in
        *"diff --git a/x b/x"*"+ok"*) ok "report build, capped: the delta is intact" ;;
        *) bad "report build, capped: the delta is intact" "out=$out" ;;
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
    case "$out" in
        *"(log truncated; full log in the run dir)"*)
            ok "report build, capped log: the truncation note is present" ;;
        *) bad "report build, capped log: the truncation note is present" "out=$out" ;;
    esac
    if [ "$(utf8_len "$out")" -le 4000 ]; then
        ok "report build, capped log: body is within --limit"
    else
        bad "report build, capped log: body is within --limit" "len=$(utf8_len "$out")"
    fi

    # --- cap step 2: --results log fields stripped, with a note ---
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
        ok "report build, oversized results log field: exits 0"
    else
        bad "report build, oversized results log field: exits 0" \
            "rc=$rc err=$err"
    fi
    case "$out" in
        *"VERDICT pr-run -> success"*) ok "report build, log-stripped: the verdict is intact" ;;
        *) bad "report build, log-stripped: the verdict is intact" "out=$out" ;;
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
    case "$out" in
        *"(log stripped; see the run dir)"*)
            ok "report build, log-stripped: the stripped-log note is present" ;;
        *) bad "report build, log-stripped: the stripped-log note is present" "out=$out" ;;
    esac
    if [ "$(utf8_len "$out")" -le 1000 ]; then
        ok "report build, log-stripped: body is within --limit"
    else
        bad "report build, log-stripped: body is within --limit" "len=$(utf8_len "$out")"
    fi

    # --- cap order: --log exhausts before results logs are stripped ---
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

    probe_b5b() {
        "$PY" "$REPORT" build --map "$GOODMAP" --limit "$1" \
            --verdict "$TOP/b5b/verdict.txt" --delta "$TOP/b5b/delta.txt" \
            --results "$TOP/b5b/results.json" --log "combolog=$TOP/b5b/log.txt"
    }
    "$PY" "$REPORT" build --map "$GOODMAP" --limit 1000000 \
        --verdict "$TOP/b5b/verdict.txt" --delta "$TOP/b5b/delta.txt" \
        --results "$TOP/b5b/results.json" --log "combolog=$TOP/b5b/log.txt" \
        > "$TOP/b5b/full.out"
    full_len=$(file_len "$TOP/b5b/full.out")
    boundary=$(find_boundary 'COMBOLOGDETAIL-B5B-PAYLOAD' 1 "$full_len" probe_b5b)

    capture out err rc probe_b5b "$boundary"
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
        *"(log truncated; full log in the run dir)"*)
            ok "report build, cap order at the log-exhausted size: the log-truncated note is present" ;;
        *) bad "report build, cap order at the log-exhausted size: the log-truncated note is present" "out=$out" ;;
    esac
    case "$out" in
        *"COMBOLOGDETAIL-B5B-PAYLOAD"*)
            ok "report build, cap order at the log-exhausted size: the results log field survives" ;;
        *) bad "report build, cap order at the log-exhausted size: the results log field survives" "out=$out" ;;
    esac

    capture out err rc probe_b5b "$((boundary - 1))"
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
            bad "report build, cap order one byte tighter: the results log field is stripped" "out=$out" ;;
        *) ok "report build, cap order one byte tighter: the results log field is stripped" ;;
    esac
    case "$out" in
        *"(log stripped; see the run dir)"*)
            ok "report build, cap order one byte tighter: the stripped-log note is present" ;;
        *) bad "report build, cap order one byte tighter: the stripped-log note is present" "out=$out" ;;
    esac
    case "$out" in
        *"test_render_large_log"*)
            ok "report build, cap order one byte tighter: the case's own identity survives" ;;
        *) bad "report build, cap order one byte tighter: the case's own identity survives" "out=$out" ;;
    esac
    if [ "$(utf8_len "$out")" -le "$((boundary - 1))" ]; then
        ok "report build, cap order one byte tighter: body is within --limit"
    else
        bad "report build, cap order one byte tighter: body is within --limit" "len=$(utf8_len "$out")"
    fi

    # --- cap step 3: delta becomes `git apply --stat` + head + note ---
    mkdir -p "$TOP/b5c"
    printf 'VERDICT pr-run -> success\n' > "$TOP/b5c/verdict.txt"
    "$PY" -c '
for i in range(30):
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
    EXPECTED_STAT=$(git apply --stat "$TOP/b5c/delta.txt")
    "$PY" - <<PYEOF > "$TOP/b5c/results.json"
import json
biglog = "DELTAORDER-B5C-PAYLOAD " * 100
data = {"configuration": {}, "result": {
    "wisekiosk.WiseKioskTest.test_backend_unit_active": {"status": "PASSED"},
    "wisekiosk.WiseKioskTest.test_render_large_log": {"status": "FAILED", "log": biglog},
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

    probe_b5c() {
        "$PY" "$REPORT" build --map "$GOODMAP" --limit "$1" \
            --verdict "$TOP/b5c/verdict.txt" --delta "$TOP/b5c/delta.txt" \
            --results "$TOP/b5c/results.json" --log "deltaorderlog=$TOP/b5c/log.txt"
    }
    "$PY" "$REPORT" build --map "$GOODMAP" --limit 1000000 \
        --verdict "$TOP/b5c/verdict.txt" --delta "$TOP/b5c/delta.txt" \
        --results "$TOP/b5c/results.json" --log "deltaorderlog=$TOP/b5c/log.txt" \
        > "$TOP/b5c/full.out"
    full_len_c=$(file_len "$TOP/b5c/full.out")
    boundary_c=$(find_boundary 'new line 4 of file 0029' 1 "$full_len_c" probe_b5c)

    capture out err rc probe_b5c "$boundary_c"
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
        *"new line 4 of file 0029"*)
            ok "report build, cap order at the delta-untouched size: the delta is still whole" ;;
        *) bad "report build, cap order at the delta-untouched size: the delta is still whole" "out=$out" ;;
    esac
    case "$out" in
        *"delta truncated"*)
            bad "report build, cap order at the delta-untouched size: no truncation note yet" "out=$out" ;;
        *) ok "report build, cap order at the delta-untouched size: no truncation note yet" ;;
    esac

    capture out err rc probe_b5c "$((boundary_c - 1))"
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
        *"$EXPECTED_STAT"*)
            ok "report build, cap order one byte tighter than the delta: the real git-apply --stat output is present" ;;
        *) bad "report build, cap order one byte tighter than the delta: the real git-apply --stat output is present" \
            "out=$out" ;;
    esac
    case "$out" in
        *"new line 4 of file 0029"*)
            bad "report build, cap order one byte tighter than the delta: the delta's tail is gone" "out=$out" ;;
        *) ok "report build, cap order one byte tighter than the delta: the delta's tail is gone" ;;
    esac
    case "$out" in
        *"new line 4 of file 0000"*)
            ok "report build, cap order one byte tighter than the delta: the delta's head survives" ;;
        *) bad "report build, cap order one byte tighter than the delta: the delta's head survives" "out=$out" ;;
    esac
    if [ "$(utf8_len "$out")" -le "$((boundary_c - 1))" ]; then
        ok "report build, cap order one byte tighter than the delta: body is within --limit"
    else
        bad "report build, cap order one byte tighter than the delta: body is within --limit" \
            "len=$(utf8_len "$out")"
    fi

    # --- cannot fit after every cap step ---
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
# B. tools/pipeline/report.py check -- the pre-post gate
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
    if [ "$rc" -eq 1 ] && [ "$err" = "identity found" ]; then
        ok "report check, a raw map value in the body: rc 1, reason is the identity-found constant"
    else
        bad "report check, a raw map value in the body: rc 1, reason is the identity-found constant" \
            "rc=$rc out=$out err=$err"
    fi

    capture_stdin out err rc \
        "stray mac ${mac_hi}:${mac_lo} leaked into the body" \
        "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 1 ] && [ "$err" = "identity found" ]; then
        ok "report check, a raw PATTERN token in the body: rc 1, reason is the identity-found constant"
    else
        bad "report check, a raw PATTERN token in the body: rc 1, reason is the identity-found constant" \
            "rc=$rc out=$out err=$err"
    fi

    NOFENCEMAP="$TOP/device-identity-no-fence.md"
    cat > "$NOFENCEMAP" <<'EOF'
# Fixture map with no identity fence at all -- the KNOWN half has nothing to scan.
Nothing here to redact against.
EOF
    capture_stdin out err rc \
        $'VERDICT: pr-run -> success\nclean body, no identity, no private key\n' \
        "$PY" "$REPORT" check --map "$NOFENCEMAP"
    if [ "$rc" -eq 1 ] && [ "$err" = "identity check PARTIAL" ]; then
        ok "report check, map with no usable identity-fence rows: rc 1, reason is the PARTIAL constant"
    else
        bad "report check, map with no usable identity-fence rows: rc 1, reason is the PARTIAL constant" \
            "rc=$rc out=$out err=$err"
    fi

    capture_stdin out err rc \
        $'VERDICT: pr-run -> success\nclean body, no identity, no private key\n' \
        "$PY" "$REPORT" check --map "$TOP/does-not-exist.md"
    if [ "$rc" -eq 1 ] && [ "$err" = "identity check PARTIAL" ]; then
        ok "report check, a missing map file: rc 1, reason is the PARTIAL constant"
    else
        bad "report check, a missing map file: rc 1, reason is the PARTIAL constant" \
            "rc=$rc out=$out err=$err"
    fi

    pk_body1=$(printf 'VERDICT: pr-run -> success\n%s\nfixture, not a real key\n' "$PK_HEADER")
    capture_stdin out err rc "$pk_body1" "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ "$err" = "private key material" ]; then
        ok "report check, a bare private-key header: rc 2, nothing on stdout, reason is the private-key constant"
    else
        bad "report check, a bare private-key header: rc 2, nothing on stdout, reason is the private-key constant" \
            "rc=$rc out=$out err=$err"
    fi

    pk_body2=$(printf 'VERDICT: pr-run -> success\n2026-09-30T10:00:00Z %s\nfixture, not a real key\n' \
        "$PK_HEADER_RSA")
    capture_stdin out err rc "$pk_body2" "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ "$err" = "private key material" ]; then
        ok "report check, a private-key header behind a log-timestamp prefix: rc 2, nothing on stdout, reason is the private-key constant"
    else
        bad "report check, a private-key header behind a log-timestamp prefix: rc 2, nothing on stdout, reason is the private-key constant" \
            "rc=$rc out=$out err=$err"
    fi

    capture_stdin out err rc \
        $'VERDICT: pr-run -> success\nclean body, no identity, no private key\n' \
        "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 0 ]; then
        ok "report check, no private key and no identity: rc 0"
    else
        bad "report check, no private key and no identity: rc 0" "rc=$rc out=$out err=$err"
    fi

    capture_stdin out err rc \
        "VERDICT: $BENCH_ADDR was never redacted, no private key here" \
        "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 1 ] && [ "$err" = "identity found" ]; then
        ok "report check, an identity hit with no private key: rc 1, reason is the identity-found constant"
    else
        bad "report check, an identity hit with no private key: rc 1, reason is the identity-found constant" \
            "rc=$rc out=$out err=$err"
    fi

    # A directory as --map: scrub-identity.py's own subprocess crashes
    # reading it (IsADirectoryError) -- a tool fault, not a finding.
    capture_stdin out err rc \
        $'VERDICT: pr-run -> success\nclean body, no identity, no private key\n' \
        "$PY" "$REPORT" check --map "$TOP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ "$err" = "tool failure" ]; then
        ok "report check, --map is a directory: rc 2, reason is the tool-failure constant, not identity found"
    else
        bad "report check, --map is a directory: rc 2, reason is the tool-failure constant, not identity found" \
            "rc=$rc out=$out err=$err"
    fi

    # git shim first on PATH: only `git init` fails.
    FAKEGIT="$TOP/fakegit"
    mkdir -p "$FAKEGIT"
    REALGIT=$(command -v git)
    cat > "$FAKEGIT/git" <<EOF
#!/bin/sh
if [ "\$1" = "init" ]; then exit 1; fi
exec "$REALGIT" "\$@"
EOF
    chmod +x "$FAKEGIT/git"
    capture_stdin out err rc \
        $'VERDICT: pr-run -> success\nclean body, no identity, no private key\n' \
        env PATH="$FAKEGIT:$PATH" "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 2 ]; then
        ok "report check, git unusable: refused rc 2"
    else
        bad "report check, git unusable: refused rc 2" "rc=$rc out=$out err=$err"
    fi
    if [ "$err" = "tool failure" ]; then
        ok "report check, git unusable: posted reason is the fixed constant"
    else
        bad "report check, git unusable: posted reason is the fixed constant" "err=$err"
    fi

    # git shim that fails EVERY subcommand, including `rev-parse` -- proves
    # report.py's own module load (not just _cmd_check's git calls) cannot
    # crash check outside its guarded path.
    FAKEGIT_ALL="$TOP/fakegit-all"
    mkdir -p "$FAKEGIT_ALL"
    cat > "$FAKEGIT_ALL/git" <<'EOF'
#!/bin/sh
exit 1
EOF
    chmod +x "$FAKEGIT_ALL/git"
    capture_stdin out err rc \
        $'VERDICT: pr-run -> success\nclean body, no identity, no private key\n' \
        env PATH="$FAKEGIT_ALL" "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ "$err" = "tool failure" ]; then
        ok "report check, every git subcommand fails: refused rc 2, reason is the fixed constant"
    else
        bad "report check, every git subcommand fails: refused rc 2, reason is the fixed constant" \
            "rc=$rc out=$out err=$err"
    fi

    # git entirely absent from PATH.
    EMPTYBIN="$TOP/emptybin"
    mkdir -p "$EMPTYBIN"
    capture_stdin out err rc \
        $'VERDICT: pr-run -> success\nclean body, no identity, no private key\n' \
        env PATH="$EMPTYBIN" "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ] && [ "$err" = "tool failure" ]; then
        ok "report check, git absent from PATH: refused rc 2, reason is the fixed constant"
    else
        bad "report check, git absent from PATH: refused rc 2, reason is the fixed constant" \
            "rc=$rc out=$out err=$err"
    fi

    BADUTF8=$(printf '\xff\xfeVERDICT: pr-run -> success')
    capture_stdin out err rc "$BADUTF8" "$PY" "$REPORT" check --map "$GOODMAP"
    if [ "$rc" -eq 2 ]; then
        ok "report check, invalid UTF-8 input: refused rc 2"
    else
        bad "report check, invalid UTF-8 input: refused rc 2" "rc=$rc out=$out err=$err"
    fi
    if [ "$err" = "tool failure" ]; then
        ok "report check, invalid UTF-8 input: posted reason is the fixed constant"
    else
        bad "report check, invalid UTF-8 input: posted reason is the fixed constant" "err=$err"
    fi
}

# =========================================================================
# C. tools/pipeline/report.py post
# =========================================================================

test_report_post() {
    local out err rc

    if [ ! -f "$REPORT" ]; then
        bad "report.py exists" "not found at $REPORT"
        return
    fi

    capture out err rc "$PY" "$REPORT" post --state success --description "ok" --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, missing --sha: rc 2, nothing on stdout"
    else
        bad "report post, missing --sha: rc 2, nothing on stdout" "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$REPORT" post --sha deadbeef01 --description "ok" --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, missing --state: rc 2, nothing on stdout"
    else
        bad "report post, missing --state: rc 2, nothing on stdout" "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$REPORT" post --sha deadbeef01 --state success --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, missing --description: rc 2, nothing on stdout"
    else
        bad "report post, missing --description: rc 2, nothing on stdout" "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$REPORT" post --sha deadbeef01 --state success --description "ok"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, missing --map: rc 2, nothing on stdout"
    else
        bad "report post, missing --map: rc 2, nothing on stdout" "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$REPORT" post
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, no arguments at all: rc 2, nothing on stdout"
    else
        bad "report post, no arguments at all: rc 2, nothing on stdout" "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$REPORT" post --sha deadbeef01 --state sideways \
        --description "ok" --map "$GOODMAP"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, invalid --state value: rc 2, nothing on stdout"
    else
        bad "report post, invalid --state value: rc 2, nothing on stdout" "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$REPORT" post --sha deadbeef01 --state success \
        --description "ok" --map "$GOODMAP" --pr 1
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, --pr without --body: rc 2, nothing on stdout"
    else
        bad "report post, --pr without --body: rc 2, nothing on stdout" "rc=$rc out=$out err=$err"
    fi

    capture out err rc "$PY" "$REPORT" post --sha deadbeef01 --state success \
        --description "ok" --map "$GOODMAP" --body "$TOP/does-not-matter.md"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, --body without --pr: rc 2, nothing on stdout"
    else
        bad "report post, --body without --pr: rc 2, nothing on stdout" "rc=$rc out=$out err=$err"
    fi

    # --- private key material in --description or --body refuses before
    # anything posts -- redact() has no logic to mask key material, so this
    # exercises the check half of post's guard, not the redaction half
    # (an ordinary map value would simply be redacted away before the check
    # ever saw it).
    capture out err rc "$PY" "$REPORT" post --sha deadbeef01 --state success \
        --map "$GOODMAP" --description "key: $PK_HEADER"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, private key in --description: refused rc 2, nothing on stdout"
    else
        bad "report post, private key in --description: refused rc 2, nothing on stdout" \
            "rc=$rc out=$out err=$err"
    fi

    printf 'leaked key %s\n' "$PK_HEADER" > "$TOP/post-body-dirty.md"
    capture out err rc "$PY" "$REPORT" post --sha deadbeef01 --state success \
        --map "$GOODMAP" --description "ok" --pr 1 --body "$TOP/post-body-dirty.md"
    if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
        ok "report post, private key in --body: refused rc 2, nothing on stdout"
    else
        bad "report post, private key in --body: refused rc 2, nothing on stdout" \
            "rc=$rc out=$out err=$err"
    fi

    # Fake gh shim: records every invocation's argv, one call per line
    # (tab-separated args), and answers `gh pr comment` with a fake comment
    # URL on its last stdout line -- the exact shape cmd_post reads for
    # target_url.
    FAKEGH="$TOP/fakegh"
    mkdir -p "$FAKEGH"
    FAKEGH_LOG="$TOP/fakegh.log"
    : > "$FAKEGH_LOG"
    cat > "$FAKEGH/gh" <<EOF
#!/bin/sh
{ printf '%s\t' "\$@"; printf '\n'; } >> "$FAKEGH_LOG"
if [ "\$1" = "pr" ] && [ "\$2" = "comment" ]; then
    echo "https://github.com/WisewareOrg/meta-wisekiosk/pull/1#issuecomment-1"
fi
exit 0
EOF
    chmod +x "$FAKEGH/gh"

    LONGDESC=$(printf 'x%.0s' $(seq 1 200))
    EXPECTED_DESC="${LONGDESC:0:140}"
    capture out err rc env PATH="$FAKEGH:$PATH" \
        "$PY" "$REPORT" post --sha deadbeef01 --state success --map "$GOODMAP" \
        --description "$LONGDESC"
    if [ "$rc" -eq 0 ]; then
        ok "report post, description over 140 chars: posts via the gh shim"
    else
        bad "report post, description over 140 chars: posts via the gh shim" \
            "rc=$rc out=$out err=$err"
    fi
    SENT_DESC=$(grep -o "description=$EXPECTED_DESC"$'\t' "$FAKEGH_LOG" || true)
    if [ -n "$SENT_DESC" ]; then
        ok "report post, description over 140 chars: truncated to DESCRIPTION_MAX before reaching gh"
    else
        bad "report post, description over 140 chars: truncated to DESCRIPTION_MAX before reaching gh" \
            "log=$(cat "$FAKEGH_LOG")"
    fi
    if grep -q "context=bench-pipeline"$'\t' "$FAKEGH_LOG"; then
        ok "report post: the status context is bench-pipeline"
    else
        bad "report post: the status context is bench-pipeline" "log=$(cat "$FAKEGH_LOG")"
    fi

    # --- full call shape: --pr/--body posts a comment, then a status with target_url ---
    : > "$FAKEGH_LOG"
    printf 'clean body, no identity, no private key\n' > "$TOP/post-body-clean.md"
    capture out err rc env PATH="$FAKEGH:$PATH" \
        "$PY" "$REPORT" post --sha deadbeef02 --state failure --map "$GOODMAP" \
        --description "pipeline run failed" --pr 42 --body "$TOP/post-body-clean.md"
    if [ "$rc" -eq 0 ]; then
        ok "report post, --pr/--body: posts via the gh shim"
    else
        bad "report post, --pr/--body: posts via the gh shim" "rc=$rc out=$out err=$err"
    fi
    if grep -q '^pr'$'\t''comment'$'\t''42'$'\t' "$FAKEGH_LOG"; then
        ok "report post, --pr/--body: the pr-comment call names the right PR"
    else
        bad "report post, --pr/--body: the pr-comment call names the right PR" "log=$(cat "$FAKEGH_LOG")"
    fi
    if grep -q 'target_url=https://github.com/WisewareOrg/meta-wisekiosk/pull/1#issuecomment-1' "$FAKEGH_LOG"; then
        ok "report post, --pr/--body: the comment URL is wired into the status as target_url"
    else
        bad "report post, --pr/--body: the comment URL is wired into the status as target_url" \
            "log=$(cat "$FAKEGH_LOG")"
    fi
    if grep -q 'state=failure'$'\t' "$FAKEGH_LOG"; then
        ok "report post, --pr/--body: the status call carries the given --state"
    else
        bad "report post, --pr/--body: the status call carries the given --state" "log=$(cat "$FAKEGH_LOG")"
    fi
}

# =========================================================================
# D. tools/pipeline/run.sh -- static shape
# =========================================================================

test_run_sh_shape() {
    local out err rc

    if [ ! -f "$RUNSH" ]; then
        bad "run.sh exists" "not found at $RUNSH"
        return
    fi

    cat > "$TOP/finish_exit_shape.py" <<'PYEOF'
import re
import sys

path = sys.argv[1]
with open(path) as f:
    lines = f.readlines()

call_re = re.compile(r'^\s*finish\s+("\$|failure|success|error)')
def_re = re.compile(r'^\s*finish\(\)\s*\{')

violations = []
n = len(lines)
i = 0
while i < n:
    line = lines[i]
    if def_re.match(line):
        i += 1
        continue
    if call_re.match(line):
        j = i
        while lines[j].rstrip("\n").endswith("\\"):
            j += 1
        if j + 1 < n:
            nxt = lines[j + 1].strip()
            if not nxt.startswith("exit"):
                violations.append(i + 1)
    i += 1

for v in violations:
    print(v)
PYEOF

    capture out err rc "$PY" "$TOP/finish_exit_shape.py" "$RUNSH"
    if [ -z "$out" ]; then
        ok "run.sh: every finish call exits, except the last"
    else
        bad "run.sh: every finish call exits, except the last" "violating lines: $out"
    fi

    cat > "$TOP/finish_first_token.py" <<'PYEOF'
import re
import sys

path = sys.argv[1]
with open(path) as f:
    lines = f.readlines()

def_re = re.compile(r'^\s*finish\(\)\s*\{')
first_token_re = re.compile(r'^\s*finish\b')
token_re = re.compile(r'\bfinish\b')

violations = []
for i, line in enumerate(lines):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if def_re.match(line):
        continue
    if not token_re.search(line):
        continue
    if not first_token_re.match(line):
        violations.append(i + 1)

for v in violations:
    print(v)
PYEOF

    capture out err rc "$PY" "$TOP/finish_first_token.py" "$RUNSH"
    if [ -z "$out" ]; then
        ok "run.sh: finish is only ever a line's first token outside its definition"
    else
        bad "run.sh: finish is only ever a line's first token outside its definition" "violating lines: $out"
    fi
}

test_report_build
test_report_check
test_report_post
test_run_sh_shape

echo
printf 'pass=%s fail=%s\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
