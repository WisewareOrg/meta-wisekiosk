#!/usr/bin/env bash
# Self-test for report-build.py's renderer and scrub-identity.py --filter.
#   tools/pipeline-test.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPORT="$HERE/pipeline/report-build.py"
SCRUB="$HERE/scrub-identity.py"

PY=python3
REPO_ROOT="$(cd "$HERE/.." && pwd)"
[ -x "$REPO_ROOT/.venv/bin/python3" ] && PY="$REPO_ROOT/.venv/bin/python3"

TOP=$(mktemp -d)
trap 'rm -rf "$TOP"' EXIT

pass=0; fail=0
ok()  { printf 'ok    %s\n' "$1"; pass=$((pass+1)); }
bad() { printf 'FAIL  %s\n' "$1"; [ $# -gt 1 ] && printf '        %s\n' "$2"; fail=$((fail+1)); }

# capture OUTVAR RCVAR cmd args... -- sets each var to cmd's stdout, rc.
capture() {
    local _o=$1 _r=$2; shift 2
    local _cap_out _cap_rc
    _cap_out=$("$@" 2>"$TOP/stderr"); _cap_rc=$?
    printf -v "$_o" '%s' "$_cap_out"
    printf -v "$_r" '%s' "$_cap_rc"
}

# --- report-build.py fixtures -------------------------------------------

VERDICT="$TOP/verdict.txt"
printf 'pr #1  sha: abc123  baseline: def456\nVERDICT: failure\n' > "$VERDICT"
DELTA="$TOP/delta.txt"
printf '+package-a 1.0 -> 1.1\n' > "$DELTA"

RESULTS="$TOP/testresults.json"
cat > "$RESULTS" <<'EOF'
{"5678-efgh": {"configuration": {}, "result": {
    "test_backend_unit_active": {"status": "PASSED"},
    "test_healthz": {"status": "FAILED", "log": "line1\nline2\nconnection refused\n"}
}}}
EOF

WRAPPED="$TOP/testresults-wrapped.json"
cat > "$WRAPPED" <<'EOF'
{"1234-abcd": {"configuration": {}, "result": {
    "test_page_serves": {"status": "PASSED"}
}}}
EOF

LONGLOG="$TOP/long.log"
seq 1 250 > "$LONGLOG"

# --- report-build.py assertions -----------------------------------------

capture out rc "$PY" "$REPORT" --delta "$DELTA"
if [ "$rc" -eq 2 ]; then ok "build: missing --verdict refuses (rc 2)"; else bad "missing --verdict" "rc=$rc"; fi

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --delta "$DELTA" --bogus x
if [ "$rc" -eq 2 ]; then ok "build: an unknown flag refuses (rc 2)"; else bad "unknown flag" "rc=$rc"; fi

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --delta "$DELTA" --log "$TOP/no-such-log"
if [ "$rc" -eq 0 ] && [[ "$out" == *"could not read"* ]]; then
    ok "build: a --log path that does not exist still renders (rc 0, with a note)"
else
    bad "--log missing path" "rc=$rc out=$out"
fi

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --delta "$DELTA"
if [ "$rc" -eq 0 ] && [[ "$out" == *"## Verdict"* ]] && [[ "$out" == *"VERDICT: failure"* ]] \
        && [[ "$out" == *"## Artifact delta"* ]] && [[ "$out" == *"package-a"* ]]; then
    ok "build: verdict + delta render with no results or logs"
else
    bad "verdict + delta render" "rc=$rc out=$out"
fi

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --delta "$DELTA" --results "$RESULTS"
if [ "$rc" -eq 0 ] && [[ "$out" == *"| test_backend_unit_active | PASSED |"* ]] \
        && [[ "$out" == *"| test_healthz | FAILED |"* ]] \
        && [[ "$out" == *"### test_healthz"* ]] && [[ "$out" == *"connection refused"* ]]; then
    ok "build: results table lists every case, failing log tail only for the failure"
else
    bad "results table" "rc=$rc out=$out"
fi
if [[ "$out" != *"### test_backend_unit_active"* ]]; then
    ok "build: a passing case gets no log section"
else
    bad "passing case got a log section"
fi

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --delta "$DELTA" --results "$WRAPPED"
if [ "$rc" -eq 0 ] && [[ "$out" == *"test_page_serves"* ]]; then
    ok "build: the wrapped {id: {result}} results shape also parses"
else
    bad "wrapped results shape" "rc=$rc out=$out"
fi

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --delta "$DELTA" --log "$LONGLOG"
if [ "$rc" -eq 0 ] && [[ "$out" == *"## Log — long.log"* ]] \
        && [[ "$out" == *$'\n1\n'* ]] && [[ "$out" == *$'\n250'* ]]; then
    ok "build: a --log's label is its basename, and the renderer does not re-tail it"
else
    bad "log label and no re-tail" "rc=$rc"
fi

BIGDELTA="$TOP/big-delta.txt"
"$PY" -c "print('x' * 100000)" > "$BIGDELTA"
capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --delta "$BIGDELTA"
if [ "$rc" -eq 0 ] && [ "${#out}" -gt 60000 ] && [[ "$out" != *"report truncated"* ]]; then
    ok "build: the renderer itself caps nothing -- the driver's head -c does that"
else
    bad "no renderer-side size cap" "rc=$rc len=${#out}"
fi

capture out rc "$PY" "$REPORT" --help
if [ "$rc" -eq 2 ]; then
    ok "build: --help is rejected like any other unrecognized flag (rc 2)"
else
    bad "--help no longer special-cased" "rc=$rc"
fi

# --- scrub-identity.py --filter fixtures --------------------------------
# Split: a joined literal here would trip gitleaks and scrub-identity.py's own --check.
ip_hi="10.77.4"; ip_lo="9"
STRAY_IP="${ip_hi}.${ip_lo}"
pk_dash="-----"; pk_begin="BEGIN"; pk_priv="PRIVATE"; pk_key="KEY"; pk_end="END"
PK_HEADER="${pk_dash}${pk_begin} RSA ${pk_priv} ${pk_key}${pk_dash}"
PK_FOOTER="${pk_dash}${pk_end} RSA ${pk_priv} ${pk_key}${pk_dash}"

MAP="$TOP/device-identity.md"
cat > "$MAP" <<EOF
# Fixture identity map -- RFC 5737 placeholders only.
\`\`\`identity
prod.address    = 198.51.100.7
bench.address   = 198.51.100.14
public.machine  = raspberrypi0-wifi
\`\`\`
EOF
mkdir -p "$TOP/filterroot/local"
cp "$MAP" "$TOP/filterroot/local/device-identity.md"

run_filter() { "$PY" "$SCRUB" --filter "$TOP/filterroot" < "$TOP/filter-in"; }

printf 'bench is 198.51.100.14, prod is 198.51.100.7\n' > "$TOP/filter-in"
out=$(run_filter)
if [[ "$out" == *"<bench.address>"* ]] && [[ "$out" == *"<prod.address>"* ]]; then
    ok "filter: known map values become <role.key>, longest first"
else
    bad "filter known values" "$out"
fi

printf 'stray address %s here\n' "$STRAY_IP" > "$TOP/filter-in"
out=$(run_filter)
if [[ "$out" == *"<redacted>"* ]] && [[ "$out" != *"$STRAY_IP"* ]]; then
    ok "filter: a PATTERN hit becomes <redacted>"
else
    bad "filter pattern" "$out"
fi

printf '%s\nMIIFAKEKEYDATA\n%s\n' "$PK_HEADER" "$PK_FOOTER" > "$TOP/filter-in"
out=$(run_filter)
if [[ "$out" == *"<redacted key>"* ]] && [[ "$out" != *"MIIFAKEKEYDATA"* ]]; then
    ok "filter: a PRIVATE KEY block becomes <redacted key>"
else
    bad "filter private key" "$out"
fi

printf 'machine stays raspberrypi0-wifi\n' > "$TOP/filter-in"
out=$(run_filter)
if [[ "$out" == *"raspberrypi0-wifi"* ]]; then
    ok "filter: a public.* map entry is left alone"
else
    bad "filter public namespace" "$out"
fi

rm "$TOP/filterroot/local/device-identity.md"
printf 'stray address %s, no map here\n' "$STRAY_IP" > "$TOP/filter-in"
out=$("$PY" "$SCRUB" --filter "$TOP/filterroot" < "$TOP/filter-in"); rc=$?
if [ "$rc" -eq 2 ] && [[ "$out" != *"$STRAY_IP"* ]]; then
    ok "filter: a missing map fails closed (rc 2), posting nothing"
else
    bad "filter with no map" "rc=$rc out=$out"
fi

echo
echo "pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
