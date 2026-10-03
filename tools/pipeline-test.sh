#!/usr/bin/env bash
# Self-test for report-build.py's renderer, scrub-identity.py --filter,
# install.sh's two lock gates, and kas-run.sh's PIPELINE_HASHSERV branch. Not
# wired into `just guards` or CI -- run by hand after touching any of those.
#   tools/pipeline-test.sh
set -uo pipefail

# A hook-spawned shell can set GIT_DIR and GIT_INDEX_FILE for the real repo;
# the sandbox below clones and commits into its own tree with `git -C`, which
# GIT_DIR overrides, re-pointing every git call here at that repo instead.
# Kept as a second line of defense; sgit (below) is the actual guard.
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_CONFIG_PARAMETERS GIT_PREFIX

# This tree's own .env may already carry PIPELINE_HASHSERV (install.sh writes
# it, and `just` dotenv-loads it into every recipe, including `just guards`);
# the "unset" kas-run.sh case below needs it genuinely unset, not whatever
# this operator's environment happens to hold.
unset PIPELINE_HASHSERV PIPELINE_KEYS_DIR KAS_RUN_ENV

# sgit -- every git call the sandbox makes goes through this, never a bare
# `git`. `env -i` drops the whole inherited environment rather than naming
# variables to unset, so a hook env var this file's author did not think of
# cannot leak in the same way GIT_DIR and GIT_INDEX_FILE did.
sgit() {
    env -i PATH="$PATH" HOME="$HOME" git "$@"
}

HERE="$(cd "$(dirname "$0")" && pwd)"
REPORT="$HERE/pipeline/report-build.py"
SCRUB="$HERE/scrub-identity.py"
INSTALL="$HERE/pipeline/install.sh"
KASRUN="$HERE/kas-run.sh"

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
DELTA="$TOP/delta.txt"
printf '+package-a 1.0 -> 1.1\n' > "$DELTA"

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

capture out rc "$PY" "$REPORT" --verdict "$VERDICT" --delta "$DELTA" --log "$LONGLOG"
if [ "$rc" -eq 0 ] && [[ "$out" == *"## Log — long.log"* ]] \
        && [[ "$out" == *$'\n1\n'* ]] && [[ "$out" == *$'\n250'* ]]; then
    ok "build: a --log's label is its basename, and the renderer does not re-tail it"
else
    bad "log label and no re-tail" "rc=$rc"
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

# --- install.sh lock gates ------------------------
# A fake HOME, a bare local origin, a ROOT dev tree cloned from it (carrying
# install.sh's own required files), and stub ssh/systemctl/loginctl on PATH
# so the gates can be driven without a network, a device or real systemd.

sandbox() {
    local sbx="$TOP/sbx-$1"
    mkdir -p "$sbx/home" "$sbx/bin"
    sgit init -q --bare "$sbx/origin.git"
    sgit clone -q "$sbx/origin.git" "$sbx/root" 2> /dev/null
    mkdir -p "$sbx/root/tools/pipeline" "$sbx/root/local/keys"
    cp "$INSTALL" "$sbx/root/tools/pipeline/install.sh"
    printf 'fixture\n' > "$sbx/root/local/device-identity.md"
    sgit -C "$sbx/root" -c user.email=t@t -c user.name=t add -A
    sgit -C "$sbx/root" -c user.email=t@t -c user.name=t commit -q -m init
    sgit -C "$sbx/root" push -q origin HEAD:main
    cat > "$sbx/bin/ssh" <<'STUB'
#!/bin/sh
case "$*" in
    *hostname) echo sandbox-device ;;
esac
STUB
    # Standing in for the real unit: an enable --now binds the real AF_UNIX
    # socket install.sh's fail-closed wait polls for with `[ -S ... ]`, unless
    # NO_BIND is set (the failing-unit case); is-active reports active only
    # while that socket exists, so the wait loop has something real to check
    # beyond the file merely existing.
    cat > "$sbx/bin/systemctl" <<STUB
#!/bin/sh
. "\$HOME/.config/wisekiosk/pipeline.env"
case "\$*" in
    *"enable --now"*wisekiosk-hashserv.service*)
        [ -n "\$NO_BIND" ] || $PY -c 'import socket, sys; socket.socket(socket.AF_UNIX).bind(sys.argv[1])' "\$PIPELINE_HASHSERV"
        ;;
    *is-active*wisekiosk-hashserv.service*)
        [ -S "\$PIPELINE_HASHSERV" ] && exit 0 || exit 3
        ;;
esac
exit 0
STUB
    cat > "$sbx/bin/loginctl" <<'STUB'
#!/bin/sh
[ "$1" = show-user ] && echo Linger=yes || exit 0
STUB
    chmod +x "$sbx/bin/"*
    printf '%s' "$sbx"
}

# hold LOCKFILE READYFILE -- flock's LOCKFILE exclusively in a detached bash
# (the same fcntl.flock bitbake and install.sh's own gates use), touches
# READYFILE once the lock is actually held, and sets HOLDER_PID. Called
# directly, never via $(...): a command-substitution subshell's own
# background children do not survive it exiting, so the lock would already
# be gone by the time the caller could use it. A readiness file, not a fixed
# sleep, is what the caller waits on: this environment's fork/exec latency is
# not constant enough to race against with a guess.
hold() {
    local lockfile="$1" readyfile="$2"
    rm -f "$readyfile"
    bash -c 'exec 7>>"$1"; flock -x 7; : > "$2"; sleep 30' _ "$lockfile" "$readyfile" &
    HOLDER_PID=$!
}

# await_ready READYFILE -- polls up to 5s; fails the calling check's own
# comparison (never true) if the holder did not actually acquire the lock.
await_ready() {
    for _ in $(seq 1 50); do
        [ -f "$1" ] && return 0
        sleep 0.1
    done
    return 1
}

SBX_A=$(sandbox a)
mkdir -p "$(dirname "$SBX_A/home/.config/wisekiosk/pipeline.lock")"
READY_A="$TOP/ready-a"
hold "$SBX_A/home/.config/wisekiosk/pipeline.lock" "$READY_A"
HOLDER=$HOLDER_PID
await_ready "$READY_A"
out=$(PIPELINE_TARGET=198.51.100.9 HOME="$SBX_A/home" PATH="$SBX_A/bin:$PATH" \
    "$SBX_A/root/tools/pipeline/install.sh" 2>&1); rc=$?
kill "$HOLDER" 2> /dev/null; wait "$HOLDER" 2> /dev/null
if [ -f "$READY_A" ] && [ "$rc" -eq 1 ] && [[ "$out" == *"pipeline lock held"* ]] \
        && [ ! -d "$SBX_A/home/wisekiosk-pipeline" ]; then
    ok "install.sh: the pipeline lock gate refuses before anything is cloned"
else
    bad "pipeline lock gate" "rc=$rc out=$out"
fi

SBX_B=$(sandbox b)
mkdir -p "$SBX_B/root/build"
printf '4242\n' > "$SBX_B/root/build/bitbake.lock"
READY_B="$TOP/ready-b"
hold "$SBX_B/root/build/bitbake.lock" "$READY_B"
HOLDER=$HOLDER_PID
await_ready "$READY_B"
out=$(PIPELINE_TARGET=198.51.100.9 HOME="$SBX_B/home" PATH="$SBX_B/bin:$PATH" \
    "$SBX_B/root/tools/pipeline/install.sh" 2>&1); rc=$?
kill "$HOLDER" 2> /dev/null; wait "$HOLDER" 2> /dev/null
lockcontent=$(cat "$SBX_B/root/build/bitbake.lock")
if [ -f "$READY_B" ] && [ "$rc" -eq 1 ] && [[ "$out" == *"this tree's own build is in progress"* ]] \
        && [ ! -d "$SBX_B/home/wisekiosk-pipeline" ] && [ "$lockcontent" = "4242" ]; then
    ok "install.sh: the dev build-lock gate refuses before anything is cloned, without truncating the lock"
else
    bad "dev build-lock gate" "rc=$rc out=$out lockcontent=$lockcontent"
fi

SBX_C=$(sandbox c)
out=$(PIPELINE_TARGET=198.51.100.9 HOME="$SBX_C/home" PATH="$SBX_C/bin:$PATH" \
    "$SBX_C/root/tools/pipeline/install.sh" 2>&1); rc=$?
HASHSERV_DIR_LISTING=$(ls -A "$SBX_C/home/.config/wisekiosk/hashserv" 2>&1)
if [ "$rc" -eq 0 ] && [ -d "$SBX_C/home/wisekiosk-pipeline/driver" ] \
        && [ -d "$SBX_C/home/wisekiosk-pipeline/tree" ] \
        && grep -q '^PIPELINE_HASHSERV=.*/hashserv/hashserv\.sock"$' "$SBX_C/home/.config/wisekiosk/pipeline.env" \
        && grep -q '^PIPELINE_HASHSERV_DB=.*/hashserv/hashserv\.db"$' "$SBX_C/home/.config/wisekiosk/pipeline.env" \
        && grep -q '^PIPELINE_DEV_ROOT=' "$SBX_C/home/.config/wisekiosk/pipeline.env" \
        && [ "$HASHSERV_DIR_LISTING" = "$(printf 'hashserv.db\nhashserv.sock')" ]; then
    ok "install.sh: with neither lock held, it clones both checkouts, writes the hashserv env vars, and the socket's directory holds only the socket and database"
else
    bad "install.sh clean run" "rc=$rc out=$out hashserv_dir=[$HASHSERV_DIR_LISTING]"
fi

if [ -f "$SBX_C/home/.config/wisekiosk/hashserv/hashserv.db" ] \
        && [[ "$out" == *"created an empty shared hashserv.db"* ]]; then
    ok "install.sh: with no dev db and no pipeline copy, the shared hashserv.db is created empty"
else
    bad "install.sh empty shared db" "out=$out"
fi

if grep -qF 'PIPELINE_HASHSERV="' "$SBX_C/root/.env" 2>/dev/null; then
    ok "install.sh: appends PIPELINE_HASHSERV to this tree's own .env with no opt-in"
else
    bad "install.sh .env append" "$(cat "$SBX_C/root/.env" 2>&1)"
fi

BEFORE_ENV=$(cat "$SBX_C/root/.env")
out=$(PIPELINE_TARGET=198.51.100.9 HOME="$SBX_C/home" PATH="$SBX_C/bin:$PATH" \
    "$SBX_C/root/tools/pipeline/install.sh" 2>&1); rc=$?
AFTER_ENV=$(cat "$SBX_C/root/.env")
if [ "$rc" -eq 0 ] && [ "$BEFORE_ENV" = "$AFTER_ENV" ]; then
    ok "install.sh: the .env append is idempotent"
else
    bad "install.sh .env append idempotency" "rc=$rc before=[$BEFORE_ENV] after=[$AFTER_ENV]"
fi

SBX_D=$(sandbox d)
printf 'KIOSK_HOST="root@198.51.100.1"' > "$SBX_D/root/.env"
out=$(PIPELINE_TARGET=198.51.100.9 HOME="$SBX_D/home" PATH="$SBX_D/bin:$PATH" \
    "$SBX_D/root/tools/pipeline/install.sh" 2>&1); rc=$?
ENV_LINES=$(wc -l < "$SBX_D/root/.env")
if [ "$rc" -eq 0 ] && grep -qxF 'KIOSK_HOST="root@198.51.100.1"' "$SBX_D/root/.env" \
        && grep -q '^PIPELINE_HASHSERV="' "$SBX_D/root/.env" && [ "$ENV_LINES" -eq 2 ]; then
    ok "install.sh: appending to a .env with no trailing newline starts a new line, not glued onto the last"
else
    bad "install.sh .env append onto no trailing newline" "rc=$rc lines=$ENV_LINES content=[$(cat "$SBX_D/root/.env")]"
fi

SBX_E=$(sandbox e)
out=$(PIPELINE_TARGET=198.51.100.9 HOME="$SBX_E/home" PATH="$SBX_E/bin:$PATH" NO_BIND=1 \
    "$SBX_E/root/tools/pipeline/install.sh" 2>&1); rc=$?
if [ "$rc" -eq 1 ] && [[ "$out" == *"did not come up within 10s"* ]]; then
    ok "install.sh: fails closed when the unit never actually comes up (is-active, not just -S on a stale file)"
else
    bad "install.sh fail-closed on a non-live unit" "rc=$rc out=$out"
fi

# --- kas-run.sh PIPELINE_HASHSERV branch ----------
# A stub kas-container that echoes its argv, so the branch can be checked
# without a real build. write-build-rev.sh / go-mods.py / app-lockfile.py are
# stubbed too -- kas-run.sh calls all three before exec'ing kas-container.

KASBX="$TOP/sbx-kas"
mkdir -p "$KASBX/bin" "$KASBX/repo/tools"
cp "$KASRUN" "$KASBX/repo/tools/kas-run.sh"
printf '#!/bin/sh\nexit 0\n' > "$KASBX/repo/tools/write-build-rev.sh"
printf 'import sys; sys.exit(0)\n' > "$KASBX/repo/tools/go-mods.py"
printf 'import sys; sys.exit(0)\n' > "$KASBX/repo/tools/app-lockfile.py"
printf '#!/bin/sh\nprintf %%s "$*"\n' > "$KASBX/bin/kas-container"
chmod +x "$KASBX/repo/tools/kas-run.sh" "$KASBX/repo/tools/write-build-rev.sh" "$KASBX/bin/kas-container"

out=$(PATH="$KASBX/bin:$PATH" "$KASBX/repo/tools/kas-run.sh" build kiosk-zero-w.yaml)
if [ "$out" = "build kiosk-zero-w.yaml" ]; then
    ok "kas-run.sh: PIPELINE_HASHSERV unset -- argv carries no --runtime-args"
else
    bad "kas-run.sh unset argv" "$out"
fi

out=$(PATH="$KASBX/bin:$PATH" PIPELINE_HASHSERV="$KASBX/hs/hashserv.sock" \
    "$KASBX/repo/tools/kas-run.sh" build kiosk-zero-w.yaml)
if [[ "$out" == *"--runtime-args"* ]] \
        && [[ "$out" == *"-v $KASBX/hs:/run/wisekiosk-hashserv"* ]] \
        && [[ "$out" == *"-e BB_HASHSERVE=unix:///run/wisekiosk-hashserv/hashserv.sock"* ]] \
        && [[ "$out" == *"build kiosk-zero-w.yaml" ]]; then
    ok "kas-run.sh: PIPELINE_HASHSERV set -- mounts its directory and sets BB_HASHSERVE to the in-container socket"
else
    bad "kas-run.sh set argv" "got: $out"
fi

out=$(PATH="$KASBX/bin:$PATH" PIPELINE_HASHSERV="relative/path" \
    "$KASBX/repo/tools/kas-run.sh" build x.yaml 2>&1); rc=$?
if [ "$rc" -eq 2 ] && [[ "$out" == *"absolute path"* ]]; then
    ok "kas-run.sh: a relative PIPELINE_HASHSERV is refused"
else
    bad "relative PIPELINE_HASHSERV" "rc=$rc out=$out"
fi

out=$(PATH="$KASBX/bin:$PATH" PIPELINE_HASHSERV="/has space/hashserv.sock" \
    "$KASBX/repo/tools/kas-run.sh" build x.yaml 2>&1); rc=$?
if [ "$rc" -eq 2 ] && [[ "$out" == *"whitespace"* ]]; then
    ok "kas-run.sh: a PIPELINE_HASHSERV with whitespace is refused"
else
    bad "whitespace PIPELINE_HASHSERV" "rc=$rc out=$out"
fi

echo
echo "pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
