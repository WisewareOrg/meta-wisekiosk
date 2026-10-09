#!/usr/bin/env bash
# run.sh [ref] -- build, OTA and smoke-test the merge-queue head, or a
# missing baseline for it. With a ref, builds and runs that branch's own
# head instead, as a development tool: posts nothing, tags no baseline.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(dirname "$HERE")"
REF="${1:-}"

# Self-sources the installed env when called directly, not through a
# justfile recipe that already sourced it. Runtime-generated, not a
# tracked file -- nothing for shellcheck to resolve.
if [ -z "${PIPELINE_TARGET:-}" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$HOME/.config/wisekiosk/pipeline.env"
    set +a
fi

for v in PIPELINE_DRIVER PIPELINE_TREE PIPELINE_SSH_DIR \
        PIPELINE_KEYS_DIR PIPELINE_TARGET PIPELINE_TARGET_HOSTNAME PIPELINE_TARGET_ROLE \
        PIPELINE_LOCK PIPELINE_REPLAY_PORT DL_DIR SSTATE_DIR PATH; do
    [ -n "${!v:-}" ] || { echo "run.sh: $v not set" >&2; exit 2; }
done

if [ -n "$REF" ]; then
    if [ "$(systemctl --user is-enabled wisekiosk-pipeline.timer 2>/dev/null || true)" = "enabled" ] \
            || systemctl --user is-active --quiet wisekiosk-pipeline.service; then
        echo "run.sh: refusing a ref run while the pipeline timer is enabled -- 'just pipeline-off' first" >&2
        exit 2
    fi
fi

cd "$PIPELINE_TREE"

exec 9>"$PIPELINE_LOCK"
flock -n 9 || { echo "run.sh: pipeline lock held -- another run in progress" >&2; exit 0; }

unset KAS_BUILD_DIR
PIPELINE_BUILD_DIR="$PIPELINE_TREE/build"
TREE_JUST=(just --justfile "$PIPELINE_TREE/Justfile" --working-directory "$PIPELINE_TREE")
CHECKS="$PIPELINE_TREE/tools"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
SSH_HOST="root@$PIPELINE_TARGET"
export KIOSK_HOST="$SSH_HOST"
BENCH_CA_DIR="/data/config/replay-ca"
BENCH_CA_CERT="$BENCH_CA_DIR/ca.crt"

# A ref run posts no status and tags no baseline: docs/testing.md names it
# a development tool, never something the merge gate can wait on.
POST=1
[ -z "$REF" ] || POST=0

MUTATED=""
rc=0
write_disabled() {
    mkdir -p "$PIPELINE_DRIVER/local/pipeline"
    printf '%s\n%s\n' "$(date -Is)" "$1" > "$PIPELINE_DRIVER/local/pipeline/DISABLED"
    systemctl --user disable --now wisekiosk-pipeline.timer 2>/dev/null || true
}
# cleanup_replay -- stops the replay proxy and kills the reverse tunnel, best effort.
cleanup_replay() {
    [ -n "${PROXY_PID:-}" ] && kill "$PROXY_PID" 2>/dev/null
    [ -n "${TUNNEL_PID:-}" ] && kill "$TUNNEL_PID" 2>/dev/null
    true
}
trap 'rc=$?; cleanup_replay; [ -n "$MUTATED" ] && write_disabled "run.sh exited (rc=$rc) with the device mid-OTA"' EXIT

abort() {
    MUTATED=""
    write_disabled "$1"
    echo "run.sh: ABORTED -- $1" >&2
    exit 1
}

# booted_slot HOST -- HOST's currently booted RAUC slot bootname.
booted_slot() {
    ssh "${SSH_OPTS[@]}" "$1" 'rauc status --output-format=shell' \
        | sed -n "s/^RAUC_SYSTEM_BOOTED_BOOTNAME='\(.*\)'/\1/p"
}

# hex_read HOST PATH -- PATH's bytes on HOST as a hexdump -ve '1/1 "%02x"'
# dump: busybox has no base64 applet and no long-option od, and hex is
# the byte-safe transport the keyed hash needs. One pre-assembled string,
# not separate ssh arguments: ssh joins separate command words with
# spaces and the remote shell re-parses the result, which loses this
# format string's quoting. docs/testing.md § "Running it" has the why.
hex_read() {
    # shellcheck disable=SC2029
    ssh "${SSH_OPTS[@]}" "$1" "hexdump -ve '1/1 \"%02x\"' $2"
}

# backend_env HOST -- wisekiosk.service's own MainPID environment, one ssh round trip.
BACKEND_ENV_PROBE=$(cat <<'PROBE'
tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value wisekiosk.service)/environ
PROBE
)
backend_env() {
    # shellcheck disable=SC2029
    ssh "${SSH_OPTS[@]}" "$1" "$BACKEND_ENV_PROBE"
}

# mode_token HOST -- "live"/"replay"/"void", through framework/record.py.
mode_token() {
    backend_env "$1" | python3 "$TOOLS/pipeline/mode-check.py" "$PIPELINE_REPLAY_PORT"
}

# wait_active HOST UNIT -- polls `systemctl is-active`, 1s apart, up to 30s.
wait_active() {
    local host=$1 unit=$2 deadline
    deadline=$(( $(date +%s) + 30 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        # shellcheck disable=SC2029
        if [ "$(ssh "${SSH_OPTS[@]}" "$host" systemctl is-active "$unit" 2>/dev/null)" = "active" ]; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# replay_void REASON -- the first void wins; always returns 0.
REPLAY_RC=0
REPLAY_REASON=""
replay_void() {
    [ "$REPLAY_RC" -ne 0 ] || { REPLAY_RC=1; REPLAY_REASON="$1"; }
}

# start_replay_window -- for PIPELINE_REPLAY_SET, starts the proxy and tunnel, seeds bench's /data, restarts the backend and reads MODE_START; a live run reads MODE_START directly.
MODE_START=""
start_replay_window() {
    rm -f "$RUN_DIR/replay.log" "$RUN_DIR/replay.stderr" "$RUN_DIR/bench-config.json.saved"
    if [ -z "${PIPELINE_REPLAY_SET:-}" ]; then
        MODE_START=$(mode_token "$SSH_HOST") || MODE_START=void
        [ "$MODE_START" = live ] \
            || replay_void "bench's backend was not live before the window started: mode=$MODE_START"
        return 0
    fi
    SET_DIR="$TOOLS/replay/sets/$PIPELINE_REPLAY_SET"
    CA_DIR="$PIPELINE_KEYS_DIR/replay-ca"
    [ -d "$SET_DIR" ] || { replay_void "no replay set at $SET_DIR"; return 1; }

    python3 "$TOOLS/replay/replay.py" --set "$SET_DIR" --port "$PIPELINE_REPLAY_PORT" \
        --ca "$CA_DIR" --log "$RUN_DIR/replay.log" 2> "$RUN_DIR/replay.stderr" &
    PROXY_PID=$!
    sleep 1
    if ! kill -0 "$PROXY_PID" 2>/dev/null; then
        PROXY_START_REASON=$(tail -n1 "$RUN_DIR/replay.stderr" 2>/dev/null)
        replay_void "${PROXY_START_REASON:-replay proxy failed to start for $PIPELINE_REPLAY_SET}"
        return 1
    fi

    ssh "${SSH_OPTS[@]}" -N -o ControlMaster=no -o ControlPath=none -o ExitOnForwardFailure=yes \
        -R "127.0.0.1:$PIPELINE_REPLAY_PORT:127.0.0.1:$PIPELINE_REPLAY_PORT" "$SSH_HOST" &
    TUNNEL_PID=$!
    sleep 1
    kill -0 "$TUNNEL_PID" 2>/dev/null \
        || { replay_void "replay tunnel failed to open to $SSH_HOST"; return 1; }

    ssh "${SSH_OPTS[@]}" "$SSH_HOST" cat /data/config/config.json > "$RUN_DIR/bench-config.json.saved" \
        || { replay_void "could not save bench's own config.json before seeding $PIPELINE_REPLAY_SET"; return 1; }

    printf 'HTTPS_PROXY=http://127.0.0.1:%s\nSSL_CERT_FILE=%s\nSSL_CERT_DIR=%s\n' \
            "$PIPELINE_REPLAY_PORT" "$BENCH_CA_CERT" "$BENCH_CA_DIR" \
        | ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'cat > /data/config/wisekiosk.conf' \
        || { replay_void "could not seed bench's wisekiosk.conf for $PIPELINE_REPLAY_SET"; return 1; }
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'cat > /data/config/config.json' < "$SET_DIR/config.json" \
        || { replay_void "could not seed bench's config.json for $PIPELINE_REPLAY_SET"; return 1; }

    ssh "${SSH_OPTS[@]}" "$SSH_HOST" systemctl restart wisekiosk.service \
        || { replay_void "wisekiosk.service did not restart for $PIPELINE_REPLAY_SET"; return 1; }
    wait_active "$SSH_HOST" wisekiosk.service \
        || { replay_void "wisekiosk.service did not reach active for $PIPELINE_REPLAY_SET"; return 1; }
    MODE_START=$(mode_token "$SSH_HOST") || MODE_START=void
    [ "$MODE_START" = "replay" ] \
        || { replay_void "wisekiosk.service did not come up in replay mode for $PIPELINE_REPLAY_SET"; return 1; }

    ssh "${SSH_OPTS[@]}" "$SSH_HOST" systemctl restart kiosk.service \
        || { replay_void "kiosk.service did not restart for $PIPELINE_REPLAY_SET"; return 1; }
}

# check_replay_window_end -- the mode end-read runs on every job; a replay job also checks the proxy, the tunnel, and the access log, and reads REPLAY_VALUE from it.
REPLAY_VALUE=live
check_replay_window_end() {
    MODE_END=$(mode_token "$SSH_HOST") || MODE_END=void
    if [ "$MODE_END" != "$MODE_START" ] || [ "$MODE_END" = void ]; then
        replay_void "mode changed or unreadable across the window: start=$MODE_START end=$MODE_END"
    fi
    if [ "$MODE_START" = live ] && [ "$MODE_END" = live ]; then
        REPLAY_VALUE=live
    fi
    [ -n "${PIPELINE_REPLAY_SET:-}" ] || return 0
    if [ -z "${PROXY_PID:-}" ] || ! kill -0 "$PROXY_PID" 2>/dev/null; then
        replay_void "replay proxy died mid-window for $PIPELINE_REPLAY_SET"
    fi
    if [ -z "${TUNNEL_PID:-}" ] || ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
        replay_void "replay tunnel died mid-window for $PIPELINE_REPLAY_SET"
    fi
    [ -f "$RUN_DIR/replay.log" ] || { replay_void "no replay.log for $PIPELINE_REPLAY_SET"; return 0; }
    local miss_count hit_count
    miss_count=$(grep -c ' MISS ' "$RUN_DIR/replay.log" || true)
    [ "$miss_count" -eq 0 ] || replay_void "replay.log carries $miss_count MISS line(s) for $PIPELINE_REPLAY_SET"
    hit_count=$(grep -c ' HIT ' "$RUN_DIR/replay.log" || true)
    [ "$hit_count" -ge 1 ] || replay_void "replay.log carries no HIT line for $PIPELINE_REPLAY_SET"
    REPLAY_VALUE=$(sed -n 's/^[^ ]* SERVE //p' "$RUN_DIR/replay.log" | head -n1)
    [ -n "$REPLAY_VALUE" ] || replay_void "replay.log carries no SERVE <set>@<hash> line for $PIPELINE_REPLAY_SET"
}

# stop_replay_window -- the reverse of start_replay_window, best effort past the first failure.
stop_replay_window() {
    [ -n "${PIPELINE_REPLAY_SET:-}" ] || return 0
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" rm -f /data/config/wisekiosk.conf || true
    if [ -f "$RUN_DIR/bench-config.json.saved" ]; then
        ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'cat > /data/config/config.json' < "$RUN_DIR/bench-config.json.saved" \
            || replay_void "could not restore bench's own config.json after $PIPELINE_REPLAY_SET"
    fi

    if ssh "${SSH_OPTS[@]}" "$SSH_HOST" systemctl restart wisekiosk.service \
            && wait_active "$SSH_HOST" wisekiosk.service; then
        [ "$(mode_token "$SSH_HOST" || echo void)" = live ] \
            || replay_void "bench did not return to live after restoring from $PIPELINE_REPLAY_SET"
    else
        replay_void "wisekiosk.service did not restart (or reach active) while restoring bench after $PIPELINE_REPLAY_SET"
    fi
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" systemctl restart kiosk.service || true

    cleanup_replay
    PROXY_PID=""
    TUNNEL_PID=""
}

# wait_installer_idle HOST -- polls rauc's Installer.Operation over ssh,
# sleeping 10s between tries, until it reports idle or 10 minutes of
# wall-clock time have passed -- ssh's own connection timeout counts against
# that budget, so an unreachable device/busctl consumes it via repeated
# timeouts rather than failing fast. Returns once idle; returns non-zero once
# the budget is exhausted either way.
wait_installer_idle() {
    local host=$1 deadline state
    deadline=$(( $(date +%s) + 600 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        state=$(ssh "${SSH_OPTS[@]}" "$host" \
            'busctl get-property de.pengutronix.rauc / de.pengutronix.rauc.Installer Operation' \
            2>/dev/null) || true
        case "$state" in *idle*) return 0 ;; esac
        sleep 10
    done
    return 1
}

# stage_logargs NAME LOGFILE -- fills LOGARGS with a 200-line tail of LOGFILE
# and of each bitbake failure-task log LOGFILE references.
stage_logargs() {
    LOGARGS=()
    local name=$1 logfile=$2 path hostpath tailfile
    tailfile="$RUN_DIR/$name.tail.log"
    tail -n 200 "$logfile" > "$tailfile"
    LOGARGS+=(--log "$tailfile")
    while IFS= read -r path; do
        hostpath=$path
        case "$hostpath" in
            /work/*) hostpath="$PIPELINE_TREE/${hostpath#/work/}" ;;
        esac
        tailfile="$RUN_DIR/$(basename "$hostpath")"
        tail -n 200 "$hostpath" > "$tailfile" 2>/dev/null \
            || echo "(could not read $path)" > "$tailfile"
        LOGARGS+=(--log "$tailfile")
    done < <(sed -n 's/.*Logfile of failure stored in: //p' "$logfile" 2>/dev/null)
}

# finish STATE TEXT [report-build.py args...] -- assembles the report body;
# for a queue job (POST=1) also posts the status and PR comment on $SHA.
# Always exits 0.
finish() {
    MUTATED=""
    local state=$1 text=$2; shift 2
    printf 'pr #%s  sha: %s  baseline: %s\nVERDICT: %s\n' \
        "$PR_NUMBER" "$SHA" "$BASELINE" "$text" > "$RUN_DIR/verdict.txt"
    python3 "$TOOLS/pipeline/report-build.py" --verdict "$RUN_DIR/verdict.txt" \
            "$@" > "$RUN_DIR/body.raw" \
        || abort "could not assemble the report body for $SHA"
    "$TOOLS/scrub-identity.py" --filter "$PIPELINE_DRIVER" \
            < "$RUN_DIR/body.raw" > "$RUN_DIR/body.full" \
        || abort "identity map unavailable"
    head -c 60000 "$RUN_DIR/body.full" > "$RUN_DIR/body.md"
    if [ "$POST" -eq 1 ]; then
        local comment_url
        comment_url=$(gh pr comment "$PR_NUMBER" --body-file "$RUN_DIR/body.md" | tail -n1) \
            || abort "could not post the PR comment for $SHA"
        gh api "repos/:owner/:repo/statuses/$SHA" -f state="$state" -f context=bench-pipeline \
                -f description="${text:0:140}" -f target_url="$comment_url" > /dev/null \
            || abort "could not post the status for $SHA"
    fi
    exit 0
}

# run_or_fail NAME LOGFILE cmd... -- on failure, finishes "NAME failed" with
# NAME's own log tail and any bitbake failure-task logs attached.
run_or_fail() {
    local name=$1 log=$2; shift 2
    "$@" > "$log" 2>&1 && return 0
    stage_logargs "$name" "$log"
    finish failure "$name failed" "${LOGARGS[@]}"
}

if [ -z "$REF" ]; then
    git -C "$PIPELINE_DRIVER" fetch --quiet origin \
        || abort "git fetch origin failed in $PIPELINE_DRIVER"
    if [ "$(git -C "$PIPELINE_DRIVER" rev-parse HEAD)" != "$(git -C "$PIPELINE_DRIVER" rev-parse origin/main)" ]; then
        git -C "$PIPELINE_DRIVER" checkout --quiet --detach origin/main \
            || abort "could not check out origin/main in $PIPELINE_DRIVER"
        exec "$PIPELINE_DRIVER/tools/pipeline/run.sh" "$@"
    fi
fi

# tag_job_baseline -- tags the job's buildhistory commit JOB_BH as
# baseline/$SHA, so the next queue job's BASELINE finds it. Leaves an
# existing tag untouched. Call only on a success outcome, before finish.
tag_job_baseline() {
    git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse --verify -q "refs/tags/baseline/$SHA" \
            > /dev/null 2>&1 \
        || git -C "$PIPELINE_BUILD_DIR/buildhistory" tag "baseline/$SHA" "$JOB_BH" \
        || abort "could not tag baseline/$SHA"
}

git fetch origin || abort "git fetch origin failed in $PIPELINE_TREE"

if [ -n "$REF" ]; then
    git rev-parse --verify -q "refs/remotes/origin/$REF" > /dev/null 2>&1 \
        || { echo "run.sh: $REF is not a branch on origin" >&2; exit 2; }
    QUEUE_SHA=$(git rev-parse "refs/remotes/origin/$REF") || abort "could not resolve $REF"
    PR_NUMBER="ref:$REF"
    BASELINE=$(git merge-base origin/main "$QUEUE_SHA") \
        || abort "could not compute a merge-base of origin/main and $REF"
else
    QUEUE_REFS=$(git ls-remote origin 'refs/heads/gh-readonly-queue/main/*') \
        || abort "git ls-remote for the merge queue failed"
    CURRENT_MAIN=$(git rev-parse origin/main) || abort "could not resolve origin/main"
    MATCHING=$(printf '%s\n' "$QUEUE_REFS" | awk -F'\t' -v base="$CURRENT_MAIN" '
        { n = split($2, a, "/"); ref = a[n]
          if (ref ~ /^pr-[0-9]+-[0-9a-f]+$/) {
              split(ref, b, "-")
              if (b[3] == base) print $1 "\t" b[2] "\t" $2
          }
        }')
    MATCH_COUNT=$(printf '%s\n' "$MATCHING" | grep -c . || true)
    if [ "$MATCH_COUNT" -eq 0 ]; then
        echo "run.sh: no job" >&2
        exit 0
    elif [ "$MATCH_COUNT" -gt 1 ]; then
        echo "run.sh: more than one gh-readonly-queue ref based on origin/main" >&2
        exit 2
    fi
    QUEUE_SHA=$(printf '%s' "$MATCHING" | cut -f1)
    PR_NUMBER=$(printf '%s' "$MATCHING" | cut -f2)
    QUEUE_REF=$(printf '%s' "$MATCHING" | cut -f3)
    git fetch --quiet origin "$QUEUE_REF" || abort "could not fetch $QUEUE_REF"
    BASELINE=$(git rev-parse "$QUEUE_SHA^1") || abort "could not resolve $QUEUE_SHA^1"
fi

if git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse --verify -q \
        "refs/tags/baseline/$BASELINE" > /dev/null 2>&1; then
    KIND=queue; SHA=$QUEUE_SHA
else
    KIND=baseline; SHA=$BASELINE
fi

# A ref run never builds or tags a baseline -- it is a development tool,
# not a path that can advance the merge gate's own history.
if [ "$KIND" = baseline ] && [ -n "$REF" ]; then
    echo "run.sh: no baseline/$BASELINE tag -- a ref run never builds or tags one; run a queue job on main first to create it" >&2
    exit 2
fi

RUN_DIR="$PIPELINE_DRIVER/local/pipeline/runs/$SHA"
mkdir -p "$RUN_DIR"

if [ "$KIND" = baseline ]; then
    git checkout --detach "$SHA" > "$RUN_DIR/checkout.log" 2>&1 \
        || abort "could not check out $SHA in $PIPELINE_TREE"
    PREV_TIP=$(git rev-parse "$SHA^1") || abort "could not resolve $SHA^1"
    if git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse --verify -q \
            "refs/tags/baseline/$PREV_TIP" > /dev/null 2>&1; then
        git -C "$PIPELINE_BUILD_DIR/buildhistory" reset --hard "refs/tags/baseline/$PREV_TIP" \
            || abort "could not reset buildhistory to baseline/$PREV_TIP"
        git -C "$PIPELINE_BUILD_DIR/buildhistory" clean -fdq \
            || abort "could not clean buildhistory before the baseline build"
    fi
    "$TOOLS/pipeline/hashserv-check.sh" || abort "bitbake-hashserv check failed"
    "${TREE_JUST[@]}" build > "$RUN_DIR/build.log" 2>&1 || abort "baseline build failed"
    git -C "$PIPELINE_BUILD_DIR/buildhistory" tag -f "baseline/$SHA" \
        || abort "could not tag baseline/$SHA"
    exit 0
fi

OBSERVED_HOSTNAME=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" hostname 2>/dev/null || true)
[ "$OBSERVED_HOSTNAME" = "$PIPELINE_TARGET_HOSTNAME" ] \
    || abort "PIPELINE_TARGET's live hostname does not match PIPELINE_TARGET_HOSTNAME"

# The /data precondition. docs/testing.md § "Running it" has the why.
MAC_FILE="$PIPELINE_DRIVER/local/pipeline/bench-config.mac"
[ -f "$MAC_FILE" ] \
    || abort "bench /data differs from the accepted configuration; run just pipeline-accept-bench-config"
EXPECTED_KIOSK_CONF_MAC=$(sed -n 's/^kiosk_conf_mac=//p' "$MAC_FILE")
EXPECTED_CONFIG_MAC=$(sed -n 's/^config_mac=//p' "$MAC_FILE")
EXPECTED_CA_CERT_MAC=$(sed -n 's/^ca_cert_mac=//p' "$MAC_FILE")

HMAC_KEY="$PIPELINE_KEYS_DIR/hmac.key"
OBSERVED_KIOSK_CONF_MAC=absent
if OBSERVED_KIOSK_CONF_HEX=$(hex_read "$SSH_HOST" /data/config/kiosk.conf 2>/dev/null); then
    OBSERVED_KIOSK_CONF_MAC=$(printf '%s' "$OBSERVED_KIOSK_CONF_HEX" \
        | python3 "$TOOLS/pipeline/config-mac.py" "$HMAC_KEY")
fi
OBSERVED_CONFIG_JSON_HEX=$(hex_read "$SSH_HOST" /data/config/config.json)
OBSERVED_CONFIG_MAC=$(printf '%s' "$OBSERVED_CONFIG_JSON_HEX" \
    | python3 "$TOOLS/pipeline/config-mac.py" "$HMAC_KEY")
OBSERVED_CA_CERT_MAC=absent
if OBSERVED_CA_CERT_HEX=$(hex_read "$SSH_HOST" "$BENCH_CA_CERT" 2>/dev/null); then
    OBSERVED_CA_CERT_MAC=$(printf '%s' "$OBSERVED_CA_CERT_HEX" \
        | python3 "$TOOLS/pipeline/config-mac.py" "$HMAC_KEY")
fi

if [ "$OBSERVED_KIOSK_CONF_MAC" != "$EXPECTED_KIOSK_CONF_MAC" ] \
        || [ "$OBSERVED_CONFIG_MAC" != "$EXPECTED_CONFIG_MAC" ] \
        || [ "$OBSERVED_CA_CERT_MAC" != "$EXPECTED_CA_CERT_MAC" ]; then
    abort "bench /data differs from the accepted configuration; run just pipeline-accept-bench-config"
fi
ssh "${SSH_OPTS[@]}" "$SSH_HOST" test -e /data/config/wisekiosk.conf \
    && abort "bench carries a /data/config/wisekiosk.conf outside a replay window; remove it by hand"

git checkout --detach "$SHA" > "$RUN_DIR/checkout.log" 2>&1 \
    || abort "could not check out $SHA in $PIPELINE_TREE"
PREV_SLOT=$(booted_slot "$SSH_HOST") || abort "could not read the booted slot before install"

git -C "$PIPELINE_BUILD_DIR/buildhistory" reset --hard "refs/tags/baseline/$BASELINE" \
    || abort "could not reset buildhistory to baseline/$BASELINE"
git -C "$PIPELINE_BUILD_DIR/buildhistory" clean -fdq \
    || abort "could not clean buildhistory before the job build"
"$TOOLS/pipeline/hashserv-check.sh" || abort "bitbake-hashserv check failed"
run_or_fail build "$RUN_DIR/build.log" "${TREE_JUST[@]}" build

BASELINE_BH=$(git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse "refs/tags/baseline/$BASELINE") \
    || abort "could not read the baseline buildhistory commit"
JOB_BH=$(git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse HEAD) \
    || abort "could not read the job's buildhistory commit"
[ "$JOB_BH" != "$BASELINE_BH" ] || abort "buildhistory did not commit for $SHA"

run_or_fail bundle "$RUN_DIR/bundle.log" "${TREE_JUST[@]}" kiosk-bundle
run_or_fail image-content "$RUN_DIR/image-content.log" "${TREE_JUST[@]}" oe-test 127.0.0.1 kiosk_image.case
run_or_fail preflight "$RUN_DIR/preflight.log" "${TREE_JUST[@]}" kiosk-preflight
run_or_fail send "$RUN_DIR/send.log" "${TREE_JUST[@]}" kiosk-send-direct
MUTATED=1
if ! "${TREE_JUST[@]}" kiosk-install > "$RUN_DIR/install.log" 2>&1; then
    wait_installer_idle "$SSH_HOST" \
        || echo "installer never reported idle (or the device was unreachable); marking the other slot bad anyway" >> "$RUN_DIR/install.log"
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'rauc status mark-bad other' >> "$RUN_DIR/install.log" 2>&1 \
        || echo "could not mark the other slot bad after the failed install" >> "$RUN_DIR/install.log"
    stage_logargs install "$RUN_DIR/install.log"
    finish failure "install failed" "${LOGARGS[@]}"
fi

DEVICE_BACK=1
"${TREE_JUST[@]}" kiosk-reboot "$SSH_HOST" 180 > "$RUN_DIR/reboot.log" 2>&1 || DEVICE_BACK=0
NEW_SLOT=""
if [ "$DEVICE_BACK" -eq 1 ]; then
    NEW_SLOT=$(booted_slot "$SSH_HOST") || abort "could not read the booted slot after install"
fi
if [ "$DEVICE_BACK" -eq 0 ] || [ "$NEW_SLOT" = "$PREV_SLOT" ]; then
    finish failure "new slot did not boot"
fi

# Buildinfo readback: the same awk/sed tools/reproducibility-gate.sh uses
# on an offline image, read here from the live board instead.
# docs/testing.md § "Running it" has the why.
BUILDINFO=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" cat /etc/buildinfo 2>/dev/null | tr -d '\r' || true)
BOOTED_REV=$(printf '%s\n' "$BUILDINFO" | awk '$1 == "meta-wisekiosk" && $2 == "=" { print $3; exit }')
BOOTED_SHA=${BOOTED_REV##*:}

RESULTSARG=()
LOGARGS=()
TRANSPORT_RC=0
DIRTY_RC=0

if [ "$BOOTED_SHA" != "$SHA" ]; then
    SMOKE_STATE=failure
    SMOKE_TEXT="pr #$PR_NUMBER $SHA: smoke failure (booted slot carries $BOOTED_SHA, not $SHA)"
else
    rm -rf "$PIPELINE_TREE/local/pipeline/runs/$SHA/smoke"
    mkdir -p "$PIPELINE_TREE/local/pipeline/runs/$SHA/smoke"
    export TEST_TARGET_IP="$PIPELINE_TARGET"
    export OEQA_JSON_RESULT_DIR="/work/local/pipeline/runs/$SHA/smoke"
    export KIOSK_TARGET_ROLE="$PIPELINE_TARGET_ROLE"
    export KIOSK_TARGET_HOSTNAME="$PIPELINE_TARGET_HOSTNAME"

    TESTIMAGE_RC=0
    if start_replay_window; then
        "${TREE_JUST[@]}" testimage > "$RUN_DIR/testimage.log" 2>&1 || TESTIMAGE_RC=$?
    else
        TESTIMAGE_RC=1
    fi

    RENDER_RC=0
    "$CHECKS/kiosk-render-check.sh" "$SSH_HOST" > "$RUN_DIR/render.log" 2>&1 || RENDER_RC=$?
    GPU_RC=0
    "$CHECKS/kiosk-gpu-check.sh" "$SSH_HOST" > "$RUN_DIR/gpu.log" 2>&1 || GPU_RC=$?

    check_replay_window_end

    RESULTS_JSON="$PIPELINE_TREE/local/pipeline/runs/$SHA/smoke/testresults.json"
    RECORD_RC=0
    RECORD_REASON=""
    if [ -f "$RESULTS_JSON" ]; then
        cp "$RESULTS_JSON" "$RUN_DIR/testresults.json"
        RESULTSARG=(--results "$RUN_DIR/testresults.json")

        # The record precondition. docs/testing.md § "Running it" has the why.
        RECORD_CHECK=$(python3 "$TOOLS/pipeline/record-check.py" "$RUN_DIR/testresults.json" "$SHA" --replay "$REPLAY_VALUE")
        read -r RECORD_STATUS _ RECORD_DIRTY RECORD_TRANSPORT RECORD_REASON <<< "$RECORD_CHECK"
        [ "$RECORD_TRANSPORT" = "1" ] && TRANSPORT_RC=1
        if [ "$RECORD_STATUS" != "OK" ]; then
            RECORD_RC=1
        elif [ "$RECORD_DIRTY" = "1" ]; then
            DIRTY_RC=1
        elif [ "$RECORD_DIRTY" != "0" ]; then
            RECORD_RC=1
            RECORD_REASON="run record names dirty=$RECORD_DIRTY, not 0 or 1"
        fi
    else
        RECORD_RC=1
        RECORD_REASON="no run record"
    fi
    [ "$RECORD_RC" -eq 0 ] || stage_logargs testimage "$RUN_DIR/testimage.log"

    if [ "$RENDER_RC" -ne 0 ]; then
        tail -n 200 "$RUN_DIR/render.log" > "$RUN_DIR/render.tail.log"
        LOGARGS+=(--log "$RUN_DIR/render.tail.log")
    fi
    if [ "$GPU_RC" -ne 0 ]; then
        tail -n 200 "$RUN_DIR/gpu.log" > "$RUN_DIR/gpu.tail.log"
        LOGARGS+=(--log "$RUN_DIR/gpu.tail.log")
    fi

    stop_replay_window

    if [ "$TESTIMAGE_RC" -eq 0 ] && [ "$RENDER_RC" -eq 0 ] && [ "$GPU_RC" -eq 0 ] && [ "$RECORD_RC" -eq 0 ]; then
        SMOKE_STATE=success
    else
        SMOKE_STATE=failure
    fi
    SMOKE_TEXT="pr #$PR_NUMBER $SHA: smoke $SMOKE_STATE"
    [ "$RECORD_RC" -eq 0 ] || SMOKE_TEXT="$SMOKE_TEXT ($RECORD_REASON)"
fi

"${TREE_JUST[@]}" kiosk-rollback > "$RUN_DIR/rollback.log" 2>&1 \
    || abort "could not mark the booted slot bad"
"${TREE_JUST[@]}" kiosk-reboot > "$RUN_DIR/rollback-reboot.log" 2>&1 \
    || abort "device did not come back after the rollback reboot"
SLOT_NOW=$(booted_slot "$SSH_HOST") || abort "could not read the booted slot after the rollback"
[ "$SLOT_NOW" = "$PREV_SLOT" ] || abort "device resting on the job's slot"

# A dirty tree is an infrastructure problem with the checkout the job ran
# from, not the candidate's -- abort, never posted. docs/testing.md §
# "Running it" has the why.
[ "$DIRTY_RC" -eq 0 ] || abort "run record reports a dirty tree"

# docs/testing.md § "The render and applied cases" has the why.
[ "$TRANSPORT_RC" -eq 0 ] || abort "testimage transport error"

# docs/testing.md § "Running it" ("Replay mode") has the why.
[ "$REPLAY_RC" -eq 0 ] || abort "$REPLAY_REASON"

[ "$SMOKE_STATE" = success ] && [ "$POST" -eq 1 ] && tag_job_baseline

finish "$SMOKE_STATE" "$SMOKE_TEXT" \
    "${RESULTSARG[@]}" "${LOGARGS[@]}"
