#!/usr/bin/env bash
# Self-test for report-build.py's renderer and scrub-identity.py --filter.
#   tools/pipeline-test.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPORT="$HERE/pipeline/report-build.py"
RUN_SH="$HERE/pipeline/run.sh"
ACCEPT_SH="$HERE/pipeline/accept-bench-config.sh"
RECORD_CHECK_PY="$HERE/pipeline/record-check.py"
KIOSK_PY="$HERE/../meta-wisekiosk/lib/oeqa/runtime/cases/kiosk.py"
RECORD_PY="$HERE/../meta-wisekiosk/lib/wisekiosk/record/__init__.py"
SCRUB="$HERE/scrub-identity.py"

PY=python3

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

RESULTS="$TOP/testresults.json"
cat > "$RESULTS" <<'EOF'
{"5678-efgh": {"configuration": {}, "result": {
    "test_backend_unit_active": {"status": "PASSED"},
    "test_healthz": {"status": "FAILED", "log": "line1\nline2\nconnection refused\n"}
}}}
EOF

LONGLOG="$TOP/long.log"
seq 1 250 > "$LONGLOG"

# --- report-build.py assertions -----------------------------------------

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --log "$TOP/no-such-log"
if [ "$rc" -eq 0 ] && [[ "$out" == *"could not read"* ]]; then
    ok "build: a --log path that does not exist still renders (rc 0, with a note)"
else
    bad "--log missing path" "rc=$rc out=$out"
fi

capture out rc "$PY" "$REPORT" --verdict "$VERDICT"
if [ "$rc" -eq 0 ] && [[ "$out" == *"## Verdict"* ]] && [[ "$out" == *"VERDICT: failure"* ]]; then
    ok "build: verdict renders with no results or logs"
else
    bad "verdict render" "rc=$rc out=$out"
fi

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --results "$RESULTS"
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

RECORD_RESULTS="$TOP/record-results.json"
cat > "$RECORD_RESULTS" <<'EOF'
{"5678-efgh": {"configuration": {}, "result": {
    "test_backend_unit_active": {"status": "PASSED"},
    "wisekiosk.record": {
        "tool": "R tool=oe-test tool_commit=abc dirty=0 argv=x",
        "sut": "R sut browser=surf nrestarts=0 cmdline_sha=a webkit_env=b kiosk_conf_mac=c mode=d kernel=e cpufreq_max=f timesync=g",
        "image": "R image=abc slot=A",
        "page.test_page_applied": "R page nonce=1 state=applied cards=-/- faulted=0 unreachable=0"
    }
}}}
EOF
capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --results "$RECORD_RESULTS"
if [ "$rc" -eq 0 ] && [[ "$out" == *"## Run record"* ]]; then
    rest="$out"
    order_ok=1
    for marker in "tool_commit=abc" "image=abc slot=A" "sut browser=surf" "page nonce=1"; do
        case "$rest" in
            *"$marker"*) rest="${rest#*"$marker"}" ;;
            *) order_ok=0 ;;
        esac
    done
    if [ "$order_ok" -eq 1 ]; then
        ok "build: the run record renders verbatim, tool/image/sut/page in order"
    else
        bad "run record line order" "$out"
    fi
else
    bad "run record heading" "rc=$rc out=$out"
fi
if [[ "$out" != *"wisekiosk.record"* ]]; then
    ok "build: the run record's key is left out of the case table"
else
    bad "run record key leaked into the case table" "$out"
fi
if [[ "$out" == *"| test_backend_unit_active | PASSED |"* ]]; then
    ok "build: the case table still lists every real case beside the run record"
else
    bad "case table beside run record" "$out"
fi

UNKNOWN_KEY_RESULTS="$TOP/unknown-key-results.json"
cat > "$UNKNOWN_KEY_RESULTS" <<'EOF'
{"5678-efgh": {"configuration": {}, "result": {
    "wisekiosk.record": {
        "tool": "R tool=oe-test tool_commit=abc dirty=0 argv=x",
        "image": "R image=abc slot=A",
        "replay": "R replay=cards4-live@deadbeef"
    }
}}}
EOF
capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --results "$UNKNOWN_KEY_RESULTS"
if [ "$rc" -eq 0 ] && [[ "$out" == *"R replay=cards4-live@deadbeef"* ]]; then
    ok "build: a record key the renderer does not name still renders, not dropped"
else
    bad "unknown record key dropped" "rc=$rc out=$out"
fi

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --log "$LONGLOG"
if [ "$rc" -eq 0 ] && [[ "$out" == *"## Log — long.log"* ]] \
        && [[ "$out" == *$'\n1\n'* ]] && [[ "$out" == *$'\n250'* ]]; then
    ok "build: a --log's label is its basename, and the renderer does not re-tail it"
else
    bad "log label and no re-tail" "rc=$rc"
fi

# --- boundary: the record key and transport state are defined once, in
# wisekiosk.record, and every reader imports them rather than spelling its
# own copy ------------------------------------------------------------------
RECORD_KEY=$(sed -n 's/^RECORD_KEY = "\(.*\)"$/\1/p' "$RECORD_PY")
if [ -n "$RECORD_KEY" ] && grep -qF 'record.RECORD_KEY' "$KIOSK_PY" \
        && grep -qF 'record.RECORD_KEY' "$RECORD_CHECK_PY" \
        && grep -qF '_record.RECORD_KEY' "$REPORT"; then
    ok "boundary: kiosk.py, record-check.py and report-build.py all import record.RECORD_KEY ($RECORD_KEY)"
else
    bad "a reader spells the record key itself instead of importing wisekiosk.record.RECORD_KEY"
fi
if grep -qF 'record.TRANSPORT_STATE' "$KIOSK_PY" && grep -qF 'record.TRANSPORT_STATE' "$RECORD_CHECK_PY"; then
    ok "boundary: kiosk.py and record-check.py both import record.TRANSPORT_STATE"
else
    bad "the declared transport state is not imported consistently"
fi
# --- ssh-quoting regression: ssh joins separate remote-command words
# with spaces, and the remote shell re-parses the result -- a format
# string quoted for *local* bash does not survive that round trip unless
# the whole command reaches ssh as one argument. Simulates exactly that
# join, through sh -c, never by calling hexdump with its own argv (which
# always works and would hide the bug).
HEXFIXTURE="$TOP/hexfixture-quoting"
printf 'KIOSK_INSPECTOR=0\n' > "$HEXFIXTURE"

simulate_ssh_remote_command() {
    # ssh concatenates its remaining arguments with spaces and hands the
    # result to the remote shell for re-parsing -- "$*" is that exact join.
    sh -c "$*"
}

if simulate_ssh_remote_command hexdump -ve '1/1 "%02x"' "$HEXFIXTURE" > /dev/null 2>&1; then
    bad "ssh-quoting: the split-argv form unexpectedly succeeded -- this check no longer isolates the bug"
else
    ok "ssh-quoting: the split-argv form fails under ssh's own join (the bug is real)"
fi

FIXED_CMD="hexdump -ve '1/1 \"%02x\"' $HEXFIXTURE"
GOT=$(simulate_ssh_remote_command "$FIXED_CMD")
WANT=$(hexdump -ve '1/1 "%02x"' "$HEXFIXTURE")
if [ -n "$GOT" ] && [ "$GOT" = "$WANT" ]; then
    ok "ssh-quoting: the one-string form survives ssh's join and decodes correctly"
else
    bad "ssh-quoting: the one-string form does not survive ssh's join" "got=$GOT want=$WANT"
fi

for f in "$RUN_SH" "$ACCEPT_SH"; do
    HEX_READ_DEFS=$(grep -c '^hex_read() {' "$f")
    # The single quotes are the point: this is a literal fragment to
    # match in the target file, not an expression to expand here.
    # shellcheck disable=SC2016
    if [ "$HEX_READ_DEFS" -eq 1 ] && grep -qF '"hexdump -ve' "$f"; then
        ok "ssh-quoting: $(basename "$f") defines hex_read once, as one quoted remote command"
    else
        bad "$(basename "$f") does not define hex_read exactly once as one quoted remote command" \
            "hex_read definitions=$HEX_READ_DEFS"
    fi
done

# --- record-check.py posts only on an exact dirty=0. dirty=1 is left to
# run.sh's existing, unchanged abort path (STATUS stays OK; run.sh's own
# "= 1" check fires on the value). A missing or malformed dirty is a
# malformed record -- STATUS must not read OK, so run.sh's existing
# "status != OK" job-failure path catches it for free. Through the real
# script, never a copy of its logic.
dirty_fixture() {
    # $1 = the tool line's dirty token (e.g. "dirty=0 ", or "" to omit it
    # entirely) -- written at the same place a real tool line carries it.
    local dirty_token=$1
    cat > "$TOP/dirty-results.json" <<EOF
{"5678-efgh": {"configuration": {}, "result": {
    "wisekiosk.record": {
        "tool": "R tool=oe-test tool_commit=abc ${dirty_token}argv=x",
        "image": "R image=abc slot=A"
    }
}}}
EOF
}

dirty_fixture "dirty=0 "
capture out rc "$PY" "$RECORD_CHECK_PY" "$TOP/dirty-results.json" abc
if [ "$rc" -eq 0 ] && [ "$out" = "OK abc 0 0" ]; then
    ok "record-check: dirty=0 reports clean"
else
    bad "record-check: dirty=0 did not report clean" "rc=$rc out=$out"
fi

dirty_fixture "dirty=1 "
capture out rc "$PY" "$RECORD_CHECK_PY" "$TOP/dirty-results.json" abc
if [ "$rc" -eq 0 ] && [ "$out" = "OK abc 1 0" ]; then
    ok "record-check: dirty=1 still reports OK -- run.sh's own abort path reads the 1"
else
    bad "record-check: dirty=1 changed shape" "rc=$rc out=$out"
fi

dirty_fixture ""
capture out rc "$PY" "$RECORD_CHECK_PY" "$TOP/dirty-results.json" abc
if [ "$rc" -eq 0 ] && [[ "$out" == ERROR\ * ]] && [[ "$out" == *dirty* ]]; then
    ok "record-check: a missing dirty= is a malformed record, not clean"
else
    bad "record-check: a missing dirty= did not report malformed" "rc=$rc out=$out"
fi

dirty_fixture "dirty=yes "
capture out rc "$PY" "$RECORD_CHECK_PY" "$TOP/dirty-results.json" abc
if [ "$rc" -eq 0 ] && [[ "$out" == ERROR\ * ]] && [[ "$out" == *dirty* ]] && [[ "$out" == *yes* ]]; then
    ok "record-check: a malformed dirty=yes is a malformed record, not clean"
else
    bad "record-check: a malformed dirty value did not report malformed" "rc=$rc out=$out"
fi

# --- the shell path (hexdump | config-mac.py) agrees with hashing the
# file's bytes directly in Python, for real LF/CRLF/trailing-space content --
HEXKEY="$TOP/hexkey"
head -c 32 /dev/urandom | base64 > "$HEXKEY"
for content_name in lf crlf trailing_space; do
    case "$content_name" in
        lf) printf 'KIOSK_URL=http://localhost:8080\n' > "$TOP/hexfixture" ;;
        crlf) printf 'KIOSK_URL=http://localhost:8080\r\n' > "$TOP/hexfixture" ;;
        trailing_space) printf 'KIOSK_URL=http://localhost:8080\n \n' > "$TOP/hexfixture" ;;
    esac
    SHELL_MAC=$(hexdump -ve '1/1 "%02x"' "$TOP/hexfixture" | "$PY" "$HERE/pipeline/config-mac.py" "$HEXKEY")
    PY_MAC=$("$PY" -c "
import sys
sys.path.insert(0, '$HERE/../meta-wisekiosk/lib')
from wisekiosk import record
key = open('$HEXKEY', 'rb').read()
data = open('$TOP/hexfixture', 'rb').read()
print(record.keyed_hash(key, data))
")
    if [ -n "$SHELL_MAC" ] && [ "$SHELL_MAC" = "$PY_MAC" ]; then
        ok "shell hexdump|config-mac.py agrees with Python's direct byte hash ($content_name)"
    else
        bad "$content_name mismatch" "shell=$SHELL_MAC py=$PY_MAC"
    fi
done

# --- boundary: run.sh's buildinfo awk is the gate's own program, and both
# strip \r before it ---------------------------------------------------------
GATE_SH="$HERE/reproducibility-gate.sh"
# The single quotes are the point: this is a literal fragment of the gate's
# own source, matched with grep -F.
# shellcheck disable=SC2016
AWK_PROGRAM='$1 == "meta-wisekiosk" && $2 == "=" { print $3; exit }'
if grep -qF "$AWK_PROGRAM" "$GATE_SH" && grep -qF "$AWK_PROGRAM" "$RUN_SH"; then
    ok "boundary: run.sh's buildinfo awk is the gate's own program, not a drifted copy"
else
    bad "run.sh's buildinfo awk differs from the gate's"
fi
if grep -qF "tr -d '\r'" "$GATE_SH" && grep -qF "tr -d '\r'" "$RUN_SH"; then
    ok "boundary: run.sh strips carriage returns before awk, matching the gate"
else
    bad "run.sh does not strip carriage returns before its buildinfo awk, unlike the gate"
fi

# --- scrub-identity.py --filter fixtures --------------------------------
# Split literals: neither gitleaks nor scrub-identity.py --check matches them.
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
    ok "filter: known map values become <key>, longest first"
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
