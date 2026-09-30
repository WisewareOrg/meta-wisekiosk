#!/usr/bin/env bash
# The bench pipeline's stage driver.
#
#   run.sh                  -- run tools/pipeline/candidates.py's next job
#   run.sh baseline [<sha>] -- build & OTA a baseline run (default sha:
#                              $PIPELINE_BASELINE_REF's current HEAD)
#   run.sh pr <N>            -- build & OTA the PR's head, then always roll
#                               back to the baseline slot
#
# Reads PIPELINE_DRIVER, PIPELINE_TREE, KAS_BUILD_DIR, PIPELINE_BASELINE_REF,
# PIPELINE_SSH_DIR from the environment. PIPELINE_BASELINE_REF is a full ref,
# already qualified with its remote (e.g. `origin/main`).
#
# Stage order (a `pr` run; `baseline` is the same through the smoke, then
# marks the slot good instead of rolling back):
#
#   build -> [baseline: tag] / [pr: delta, empty -> failure, stop] -> bundle
#   -> preflight -> send -> install -> reboot (180s, then poll up to 600s
#   more for RAUC's own fallback) -> testimage -> settle 30s -> render check
#   -> gpu check -> [baseline: mark-good | pr: always mark-bad, reboot,
#   verify the baseline slot, testimage again there] -> post
#
# Bench's address is resolved each run via resolve-role.py, which refuses
# every role but bench.
#
# A pre-check failure (bench unreachable, the build dir locked or a kas
# container already running, the baseline ref or the tree checkout not
# resolvable) happens before any status is posted, and posts nothing. A
# failure after a `pending` status was posted overwrites it with `error`,
# description "run aborted: <reason>; timer disabled", and writes
# local/pipeline/DISABLED under the driver with the reason, disabling the
# timer.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(dirname "$HERE")"

: "${PIPELINE_DRIVER:?PIPELINE_DRIVER not set}"
: "${PIPELINE_TREE:?PIPELINE_TREE not set}"
: "${KAS_BUILD_DIR:?KAS_BUILD_DIR not set}"
: "${PIPELINE_BASELINE_REF:?PIPELINE_BASELINE_REF not set}"
: "${PIPELINE_SSH_DIR:?PIPELINE_SSH_DIR not set}"
export KAS_BUILD_DIR PIPELINE_SSH_DIR

PY=python3
[ -x "$PIPELINE_DRIVER/.venv/bin/python3" ] && PY="$PIPELINE_DRIVER/.venv/bin/python3"

TREE_JUST=(just --justfile "$PIPELINE_TREE/Justfile" --working-directory "$PIPELINE_TREE")

# Host-side ssh, matching every ota.just/device.just recipe -- the
# operator's ambient ~/.ssh, not PIPELINE_SSH_DIR.
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)

CONFIG="kiosk-zero-w.yaml"
MACHINE_DIR="raspberrypi0-wifi"
IMAGE="$KAS_BUILD_DIR/tmp-$MACHINE_DIR/deploy/images/$MACHINE_DIR/core-image-base-$MACHINE_DIR.rootfs.ext4"
BUNDLE="$KAS_BUILD_DIR/tmp-$MACHINE_DIR/deploy/images/$MACHINE_DIR/update-bundle-$MACHINE_DIR.raucb"

STATUS_POSTED=""
SHA="" ; KIND="" ; PR_NUMBER="" ; MERGE_BASE=""

prune_runs() {
    # Keeps the newest 20 run dirs. Runs on every exit via the trap below.
    # shellcheck disable=SC2012  # sha-named dirs, no glob-special characters
    # shellcheck disable=SC2317  # reached only through the trap
    ls -1dt "$PIPELINE_DRIVER"/local/pipeline/runs/*/ 2>/dev/null \
        | tail -n +21 | xargs -r rm -rf
}
trap prune_runs EXIT

abort() {
    # An infrastructure failure; ordinary failures use finish() instead.
    reason=$1
    mkdir -p "$PIPELINE_DRIVER/local/pipeline"
    printf '%s\n%s\n' "$(date -Is)" "$reason" > "$PIPELINE_DRIVER/local/pipeline/DISABLED"
    systemctl --user disable --now wisekiosk-pipeline.timer 2>/dev/null || true
    if [ -n "$STATUS_POSTED" ] && [ -n "$SHA" ]; then
        "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state error \
            --description "run aborted: ${reason}; timer disabled" || true
    fi
    echo "run.sh: ABORTED -- $reason" >&2
    exit 1
}

run_logged() {
    # run_logged LOGFILE -- cmd args...  (never trips set -e on a nonzero rc)
    local log=$1; shift
    set +e
    "$@" > "$log" 2>&1
    local rc=$?
    set -e
    return $rc
}

collect_failure_logs() {
    # collect_failure_logs BUILD_LOG OUT_DIR -- the last 200 lines of each
    # file bitbake named in "Logfile of failure stored in", one path per
    # line of output.
    local buildlog=$1 outdir=$2 n=0 path out
    while IFS= read -r path; do
        n=$((n + 1))
        out="$outdir/failure-$n.log"
        tail -n 200 "$path" > "$out" 2>/dev/null || echo "(could not read $path)" > "$out"
        echo "$out"
    done < <(grep -oE 'Logfile of failure stored in: .*' "$buildlog" 2>/dev/null \
            | sed 's/^Logfile of failure stored in: //')
}

booted_slot() {
    # Bootname of the currently booted RAUC slot (see
    # meta-wisekiosk/recipes-core/kiosk-netcheck).
    ssh "${SSH_OPTS[@]}" "$1" '
        eval "$(rauc status --output-format=shell)"
        for i in $RAUC_SLOTS; do
            eval state=\$RAUC_SLOT_STATE_$i
            if [ "$state" = booted ]; then
                eval echo \$RAUC_SLOT_BOOTNAME_$i
            fi
        done
    '
}

wait_for_boot() {
    # wait_for_boot HOST BEFORE_BOOT_ID SECONDS -- polls for a new boot_id;
    # never triggers a reboot itself.
    local host=$1 before=$2 seconds=$3 t0 boot_id
    t0=$(date +%s)
    while :; do
        boot_id=$(ssh "${SSH_OPTS[@]}" "$host" 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null || true)
        if [ -n "$boot_id" ] && [ "$boot_id" != "$before" ]; then
            return 0
        fi
        [ $(( $(date +%s) - t0 )) -ge "$seconds" ] && return 1
        sleep 5
    done
}

bitbake_stage() {
    # bitbake_stage NAME LOGFILE -- cmd...; on failure, attaches the last
    # 200 lines of every "Logfile of failure stored in" as --log inputs.
    local name=$1 log=$2; shift 2
    if ! run_logged "$log" "$@"; then
        local logargs=() f
        while IFS= read -r f; do logargs+=(--log "$(basename "$f")=$f"); done \
            < <(collect_failure_logs "$log" "$RUN_DIR")
        finish failure "$name failed" "${logargs[@]}"
    fi
}

ota_stage() {
    # ota_stage NAME LOGFILE -- cmd...
    local name=$1 log=$2; shift 2
    run_logged "$log" "$@" || finish failure "$name failed"
}

finish() {
    # finish STATE DESCRIPTION [report.py-build --results/--log args...]
    # Baseline runs post status only. A pr run assembles and checks the
    # full body first, withholding it if the check fails.
    local state=$1 desc=$2
    shift 2

    if [ "$KIND" = baseline ]; then
        "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state "$state" \
            --description "$desc" || true
        exit 0
    fi

    local verdict="$RUN_DIR/verdict.txt"
    {
        [ -n "${BOOT_CAVEAT:-}" ] && printf '%s\n\n' "$BOOT_CAVEAT"
        printf 'run: pr #%s  sha: %s  board: bench  baseline: %s\n' \
            "$PR_NUMBER" "$SHA" "$MERGE_BASE"
        printf 'VERDICT: %s\n' "$desc"
    } > "$verdict"

    local delta="$RUN_DIR/delta.txt"
    : > "$delta"
    [ -f "$RUN_DIR/delta-raw.txt" ] && cat "$RUN_DIR/delta-raw.txt" >> "$delta"

    local body="$RUN_DIR/report-body.md"
    if "$PY" "$TOOLS/pipeline/report.py" build \
        --map "$PIPELINE_DRIVER/local/device-identity.md" --limit 60000 \
        --verdict "$verdict" --delta "$delta" "$@" > "$body"; then
        if "$PY" "$TOOLS/pipeline/report.py" check \
            --map "$PIPELINE_DRIVER/local/device-identity.md" < "$body"; then
            "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state "$state" \
                --description "$desc" --pr "$PR_NUMBER" --body "$body" || true
        else
            "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state "$state" \
                --description "report withheld: identity check failed" || true
        fi
    else
        "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state "$state" \
            --description "$desc" || true
    fi
    exit 0
}

# --- usage: resolve KIND, SHA, PR_NUMBER --------------------------------

git -C "$PIPELINE_TREE" fetch origin \
    || { echo "run.sh: git fetch origin failed in $PIPELINE_TREE" >&2; exit 1; }

case "${1:-}" in
    "")
        job=$("$PY" "$TOOLS/pipeline/candidates.py") \
            || { echo "run.sh: candidates.py failed" >&2; exit 1; }
        if [ -z "$job" ]; then
            echo "run.sh: no candidate job" >&2
            exit 0
        fi
        # shellcheck disable=SC2086  # candidates.py's own line, word-split by design
        set -- $job
        KIND=$1; SHA=$2; PR_NUMBER=${3:-}
        ;;
    baseline)
        KIND=baseline
        if [ -n "${2:-}" ]; then
            SHA=$2
        else
            SHA=$(git -C "$PIPELINE_TREE" rev-parse "$PIPELINE_BASELINE_REF")
        fi
        ;;
    pr)
        [ -n "${2:-}" ] || { echo "usage: run.sh | run.sh baseline [<sha>] | run.sh pr <N>" >&2; exit 2; }
        KIND="pr"
        PR_NUMBER=$2
        SHA=$(gh pr view "$PR_NUMBER" --json headRefOid --jq .headRefOid)
        ;;
    *)
        echo "usage: run.sh | run.sh baseline [<sha>] | run.sh pr <N>" >&2
        exit 2
        ;;
esac

BASELINE_REMOTE="$PIPELINE_BASELINE_REF"
[ "$KIND" = pr ] && MERGE_BASE=$(git -C "$PIPELINE_TREE" merge-base "$BASELINE_REMOTE" "$SHA")

BOOT_CAVEAT=""
if [ "$KIND" = pr ] && git -C "$PIPELINE_TREE" diff --name-only "$MERGE_BASE..$SHA" \
    | grep -qE '^(includes/platforms/|meta-wisekiosk/recipes-bsp/)'; then
    BOOT_CAVEAT="rootfs only -- /boot unproven, see #104"
fi

BENCH_ADDR=$("$PY" "$TOOLS/pipeline/resolve-role.py" \
    --map "$PIPELINE_DRIVER/local/device-identity.md" bench) \
    || abort "resolve-role.py refused to resolve bench"
SSH_HOST="root@$BENCH_ADDR"

RUN_DIR="$PIPELINE_DRIVER/local/pipeline/runs/$SHA"
mkdir -p "$RUN_DIR"

LOCK="$HOME/.config/wisekiosk/pipeline.lock"
mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "run.sh: pipeline lock held -- another run in progress" >&2
    exit 0
fi

# --- pre-checks (before any status is posted) ---------------------------

ssh "${SSH_OPTS[@]}" "$SSH_HOST" true || abort "bench ($SSH_HOST) unreachable"

if [ -f "$KAS_BUILD_DIR/bitbake.lock" ] \
    && ! flock -n "$KAS_BUILD_DIR/bitbake.lock" -c true 2>/dev/null; then
    abort "bitbake.lock held in $KAS_BUILD_DIR"
fi
if docker ps --format '{{.Image}}' 2>/dev/null | grep -q '^ghcr\.io/siemens/kas/kas'; then
    abort "a kas-container is already running"
fi
git -C "$PIPELINE_TREE" rev-parse --verify -q "${BASELINE_REMOTE}^{commit}" > /dev/null \
    || abort "baseline ref $BASELINE_REMOTE does not resolve"
if [ "$KIND" = pr ]; then
    # A pr run diffs against baseline/<merge-base>, which must already be
    # tagged in buildhistory.
    git -C "$KAS_BUILD_DIR/buildhistory" rev-parse --verify -q \
        "refs/tags/baseline/$MERGE_BASE" > /dev/null \
        || abort "no baseline/$MERGE_BASE tag in $KAS_BUILD_DIR/buildhistory -- run a baseline for the merge-base first"
fi
git -C "$PIPELINE_TREE" checkout --detach "$SHA" > "$RUN_DIR/checkout.log" 2>&1 \
    || abort "could not check out $SHA in $PIPELINE_TREE"

BASELINE_SLOT=$(booted_slot "$SSH_HOST") || abort "could not read bench's booted slot"

# --- pending --------------------------------------------------------------

STATUS_POSTED=1
"$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state pending \
    --description "pipeline $KIND $(printf '%.7s' "$SHA")" || true

# --- build ------------------------------------------------------------

bitbake_stage "build" "$RUN_DIR/build.log" "${TREE_JUST[@]}" build-with-history

if [ "$KIND" = baseline ]; then
    git -C "$KAS_BUILD_DIR/buildhistory" tag -f "baseline/$SHA"
else
    set +e
    "${TREE_JUST[@]}" artifact-diff "baseline/$MERGE_BASE" HEAD \
        --repo "$KAS_BUILD_DIR/buildhistory" \
        > "$RUN_DIR/delta-raw.txt" 2> "$RUN_DIR/delta.err"
    DELTA_RC=$?
    set -e
    if [ "$DELTA_RC" -eq 1 ]; then
        finish failure "no change in image -- close as no-op"
    elif [ "$DELTA_RC" -ne 0 ]; then
        finish error "could not compute artifact delta: $(cat "$RUN_DIR/delta.err")"
    fi
fi

# --- bundle, preflight, send, install ------------------------------------

bitbake_stage "bundle" "$RUN_DIR/bundle.log" \
    "${TREE_JUST[@]}" kiosk-bundle "$CONFIG:includes/buildhistory.yaml"

ota_stage "preflight" "$RUN_DIR/preflight.log" \
    "${TREE_JUST[@]}" kiosk-preflight "$IMAGE" "$BUNDLE" "$SSH_HOST"
ota_stage "send" "$RUN_DIR/send.log" \
    "${TREE_JUST[@]}" kiosk-send-direct "$BUNDLE" "$SSH_HOST"
ota_stage "install" "$RUN_DIR/install.log" \
    "${TREE_JUST[@]}" kiosk-install "$SSH_HOST"

# --- reboot onto the new slot: 180s, then poll up to 600s more ---------

BEFORE_BOOT_ID=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" \
    'cat /proc/sys/kernel/random/boot_id' 2>/dev/null || true)
if ! run_logged "$RUN_DIR/reboot.log" "${TREE_JUST[@]}" kiosk-reboot "$SSH_HOST" 180; then
    if wait_for_boot "$SSH_HOST" "$BEFORE_BOOT_ID" 600; then
        SLOT_NOW=$(booted_slot "$SSH_HOST") \
            || abort "could not read bench's booted slot after the fallback wait"
        if [ "$SLOT_NOW" = "$BASELINE_SLOT" ]; then
            finish failure "new slot did not boot; RAUC fell back"
        else
            abort "bench came back on an unexpected slot after the new image failed to boot"
        fi
    else
        abort "bench did not come back after install"
    fi
fi

# --- testimage, settle, render, gpu --------------------------------------

STAGE="smoke"
mkdir -p "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE"
export TEST_TARGET_IP="$BENCH_ADDR"
export OEQA_JSON_RESULT_DIR="/work/local/pipeline/runs/$SHA/$STAGE"
set +e
"${TREE_JUST[@]}" testimage > "$RUN_DIR/$STAGE-testimage.log" 2>&1
TESTIMAGE_RC=$?
set -e

# oeqa's own results filename is not pinned; glob for the newest.
# shellcheck disable=SC2012  # sha-named dir, no glob-special characters
RESULTS_JSON=$(ls -t "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE"/*.json 2>/dev/null | head -1 || true)
if [ -z "$RESULTS_JSON" ]; then
    logargs=(); f=""
    while IFS= read -r f; do logargs+=(--log "$(basename "$f")=$f"); done \
        < <(collect_failure_logs "$RUN_DIR/$STAGE-testimage.log" "$RUN_DIR")
    finish error "testimage produced no results" "${logargs[@]}"
fi
cp "$RESULTS_JSON" "$RUN_DIR/$STAGE-testresults.json"

sleep 30

set +e
"$TOOLS/kiosk-render-check.sh" "$SSH_HOST" > "$RUN_DIR/$STAGE-render.log" 2>&1
RENDER_RC=$?
"$TOOLS/kiosk-gpu-check.sh" "$SSH_HOST" > "$RUN_DIR/$STAGE-gpu.log" 2>&1
GPU_RC=$?
set -e

# TESTIMAGE_RC already reflects bitbake's own pass/fail tally; a skip does
# not fail it.
SMOKE_STATE=success
[ "$TESTIMAGE_RC" -eq 0 ] || SMOKE_STATE=failure
if [ "$RENDER_RC" -eq 2 ] || [ "$GPU_RC" -eq 2 ]; then
    [ "$SMOKE_STATE" = success ] && SMOKE_STATE=error
elif [ "$RENDER_RC" -ne 0 ] || [ "$GPU_RC" -ne 0 ]; then
    SMOKE_STATE=failure
fi

# --- kind-specific finish -------------------------------------------------

if [ "$KIND" = baseline ]; then
    if [ "$SMOKE_STATE" = success ]; then
        ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'rauc status mark-good booted' \
            || abort "mark-good failed on bench after a passing baseline smoke"
        finish success "baseline $SHA: smoke passed"
    fi
    "${TREE_JUST[@]}" kiosk-rollback "$SSH_HOST" > "$RUN_DIR/rollback.log" 2>&1 || true
    if ! run_logged "$RUN_DIR/rollback-reboot.log" "${TREE_JUST[@]}" kiosk-reboot "$SSH_HOST" 180; then
        abort "bench did not come back after the baseline rollback reboot"
    fi
    SLOT_BACK=$(booted_slot "$SSH_HOST") \
        || abort "could not read bench's booted slot after the baseline rollback"
    if [ "$SLOT_BACK" != "$BASELINE_SLOT" ]; then
        abort "bench resting on the wrong slot after a baseline rollback"
    fi
    finish "$SMOKE_STATE" "baseline $SHA: smoke $SMOKE_STATE"
fi

# Always rolls back, regardless of SMOKE_STATE.
"${TREE_JUST[@]}" kiosk-rollback "$SSH_HOST" > "$RUN_DIR/rollback.log" 2>&1 || true
if ! run_logged "$RUN_DIR/rollback-reboot.log" "${TREE_JUST[@]}" kiosk-reboot "$SSH_HOST" 180; then
    abort "bench resting on PR slot"
fi
SLOT_BACK=$(booted_slot "$SSH_HOST") || abort "bench resting on PR slot"
if [ "$SLOT_BACK" != "$BASELINE_SLOT" ]; then
    abort "bench resting on PR slot"
fi

STAGE2="post-rollback"
mkdir -p "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE2"
export OEQA_JSON_RESULT_DIR="/work/local/pipeline/runs/$SHA/$STAGE2"
set +e
"${TREE_JUST[@]}" testimage > "$RUN_DIR/$STAGE2-testimage.log" 2>&1
POSTRC=$?
set -e
# shellcheck disable=SC2012  # sha-named dir, see the smoke stage above
RESULTS2=$(ls -t "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE2"/*.json 2>/dev/null | head -1 || true)
if [ -z "$RESULTS2" ]; then
    abort "post-rollback baseline smoke produced no results"
fi
cp "$RESULTS2" "$RUN_DIR/$STAGE2-testresults.json"

if [ "$POSTRC" -ne 0 ]; then
    abort "baseline slot's post-rollback smoke failed -- board may be unhealthy"
fi

finish "$SMOKE_STATE" "pr #$PR_NUMBER $SHA: smoke $SMOKE_STATE" \
    --results "pr-slot=$RUN_DIR/$STAGE-testresults.json" \
    --results "post-rollback=$RUN_DIR/$STAGE2-testresults.json"
