#!/usr/bin/env bash
# The bench pipeline's stage driver.
#
#   run.sh                  -- run tools/pipeline/candidates.py's next job
#   run.sh baseline [<sha>] -- build & OTA a baseline run (default sha:
#                              $PIPELINE_BASELINE_REF's current HEAD)
#   run.sh pr <N>            -- build & OTA the PR's head, then always roll
#                               back to the baseline slot
#
# PIPELINE_BASELINE_REF is remote-qualified, e.g. origin/main.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(dirname "$HERE")"

: "${PIPELINE_DRIVER:?PIPELINE_DRIVER not set}"
: "${PIPELINE_TREE:?PIPELINE_TREE not set}"
: "${DL_DIR:?DL_DIR not set}"
: "${SSTATE_DIR:?SSTATE_DIR not set}"
: "${PIPELINE_BASELINE_REF:?PIPELINE_BASELINE_REF not set}"
: "${PIPELINE_SSH_DIR:?PIPELINE_SSH_DIR not set}"
: "${PIPELINE_KEYS_DIR:?PIPELINE_KEYS_DIR not set}"
export DL_DIR SSTATE_DIR PIPELINE_SSH_DIR PIPELINE_KEYS_DIR

# Same lock file and fd as Justfile pipeline-install.
LOCK="$HOME/.config/wisekiosk/pipeline.lock"
mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "run.sh: pipeline lock held -- another run in progress" >&2
    exit 0
fi

# KAS_BUILD_DIR: docs/testing.md §"Running it".
unset KAS_BUILD_DIR
PIPELINE_BUILD_DIR="$PIPELINE_TREE/build"

PY=python3
[ -x "$PIPELINE_DRIVER/.venv/bin/python3" ] && PY="$PIPELINE_DRIVER/.venv/bin/python3"

TREE_JUST=(just --justfile "$PIPELINE_TREE/Justfile" --working-directory "$PIPELINE_TREE")

# Host-side ssh: the ambient ~/.ssh, not PIPELINE_SSH_DIR.
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)

CONFIG="kiosk-zero-w.yaml"
MACHINE_DIR="raspberrypi0-wifi"
IMAGE="$PIPELINE_BUILD_DIR/tmp-$MACHINE_DIR/deploy/images/$MACHINE_DIR/core-image-base-$MACHINE_DIR.rootfs.ext4"
BUNDLE="$PIPELINE_BUILD_DIR/tmp-$MACHINE_DIR/deploy/images/$MACHINE_DIR/update-bundle-$MACHINE_DIR.raucb"

STATUS_POSTED=""
SHA="" ; KIND="" ; PR_NUMBER="" ; MERGE_BASE=""
BENCH_MUTATED=""
POST_ROLLBACK_UNHEALTHY=""

# shellcheck disable=SC2317
prune_runs() {
    # Keeps the newest 20 run dirs.
    # shellcheck disable=SC2012
    ls -1dt "$PIPELINE_DRIVER"/local/pipeline/runs/*/ 2>/dev/null \
        | tail -n +21 | xargs -r rm -rf
}

write_disabled() {
    mkdir -p "$PIPELINE_DRIVER/local/pipeline"
    printf '%s\n%s\n' "$(date -Is)" "$1" > "$PIPELINE_DRIVER/local/pipeline/DISABLED"
    systemctl --user disable --now wisekiosk-pipeline.timer 2>/dev/null || true
}

# shellcheck disable=SC2317
on_exit() {
    local rc=$?
    if [ -n "$BENCH_MUTATED" ]; then
        BENCH_MUTATED=""
        write_disabled "run.sh exited (rc=$rc) with bench mid-flight"
        if [ -n "$STATUS_POSTED" ] && [ -n "$SHA" ]; then
            "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state error \
                --description "run aborted: exited with bench mid-flight; timer disabled" || true
        fi
    fi
    prune_runs
}
trap on_exit EXIT

# shellcheck disable=SC2317
on_signal() {
    echo "run.sh: received $1, exiting" >&2
    exit "$2"
}
trap 'on_signal TERM 143' TERM
trap 'on_signal INT 130' INT

abort() {
    # An infrastructure failure; ordinary failures use finish() instead.
    BENCH_MUTATED=""
    reason=$1
    write_disabled "$reason"
    if [ -n "$STATUS_POSTED" ] && [ -n "$SHA" ]; then
        "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state error \
            --description "run aborted: ${reason}; timer disabled" || true
    fi
    echo "run.sh: ABORTED -- $reason" >&2
    exit 1
}

run_logged() {
    # run_logged LOGFILE -- cmd args...
    local log=$1; shift
    set +e
    "$@" > "$log" 2>&1
    local rc=$?
    set -e
    return $rc
}

collect_failure_logs() {
    # collect_failure_logs BUILD_LOG OUT_DIR -- copies the last 200 lines of each
    # failure log bitbake names into OUT_DIR; prints one path per copy.
    local buildlog=$1 outdir=$2 n=0 path hostpath out
    local -A seen
    while IFS= read -r path; do
        hostpath=$path
        case "$hostpath" in
            /work/*) hostpath="$PIPELINE_TREE/${hostpath#/work/}" ;;
        esac
        [ -n "${seen[$hostpath]:-}" ] && continue
        seen[$hostpath]=1
        n=$((n + 1))
        out="$outdir/failure-$n.log"
        tail -n 200 "$hostpath" > "$out" 2>/dev/null || echo "(could not read $path)" > "$out"
        echo "$out"
    done < <(grep -oE 'Logfile of failure stored in: .*' "$buildlog" 2>/dev/null \
            | sed 's/^Logfile of failure stored in: //')
}

rauc_slots() {
    # rauc_slots HOST -- one line per slot:
    # "<bootname> <state> <boot_status> <primary:yes|no>".
    # RAUC_BOOT_PRIMARY is an internal slot name; RAUC_SYSTEM_SLOTS maps it
    # to RAUC_SLOTS by position.
    ssh "${SSH_OPTS[@]}" "$1" '
        eval "$(rauc status --output-format=shell)"
        set -- $RAUC_SYSTEM_SLOTS
        n=1
        primary_index=""
        for idx in $RAUC_SLOTS; do
            eval slotname=\$$n
            [ "$slotname" = "$RAUC_BOOT_PRIMARY" ] && primary_index=$idx
            n=$((n + 1))
        done
        for i in $RAUC_SLOTS; do
            eval b=\$RAUC_SLOT_BOOTNAME_$i
            eval s=\$RAUC_SLOT_STATE_$i
            eval t=\$RAUC_SLOT_BOOT_STATUS_$i
            p=no
            [ "$i" = "$primary_index" ] && p=yes
            echo "$b $s $t $p"
        done
    '
}

booted_bootname() {
    # booted_bootname SLOTS_TEXT -- the booted slot's bootname; fails if none
    awk '$2=="booted"{print $1; found=1} END{if(!found) exit 1}' <<< "$1"
}

slot_status() {
    # slot_status SLOTS_TEXT BOOTNAME -- that slot's boot_status; fails if
    # the bootname is not present
    awk -v b="$2" '$1==b{print $3; found=1} END{if(!found) exit 1}' <<< "$1"
}

primary_bootname() {
    # primary_bootname SLOTS_TEXT -- the bootname RAUC will boot next; fails
    # if none is marked primary
    awk '$4=="yes"{print $1; found=1} END{if(!found) exit 1}' <<< "$1"
}

wait_for_boot() {
    # wait_for_boot HOST BEFORE_BOOT_ID SECONDS -- polls for a new boot_id
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

LAST_BOOT_ID_BEFORE=""

reboot_and_wait() {
    # reboot_and_wait HOST LOGFILE SECONDS -- reboots, waits for a new boot_id,
    # and sets LAST_BOOT_ID_BEFORE.
    local host=$1 log=$2 seconds=$3
    LAST_BOOT_ID_BEFORE=$(ssh "${SSH_OPTS[@]}" "$host" 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null || true)
    {
        echo "boot_id before: $LAST_BOOT_ID_BEFORE"
        ssh "${SSH_OPTS[@]}" "$host" 'systemctl reboot'
    } > "$log" 2>&1 || true
    if wait_for_boot "$host" "$LAST_BOOT_ID_BEFORE" "$seconds"; then
        echo "boot_id after: $(ssh "${SSH_OPTS[@]}" "$host" 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null || true)" >> "$log"
        return 0
    fi
    echo "did not come back within ${seconds}s" >> "$log"
    return 1
}

bitbake_stage() {
    # bitbake_stage NAME LOGFILE -- cmd...; on failure, finishes with each failure log as --log.
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

refresh_remote() {
    # Fetches origin's refs for tools/reproducibility-gate.sh, which never fetches.
    git -C "$PIPELINE_TREE" fetch --quiet origin || true
}

finish() {
    # finish STATE DESCRIPTION [report.py-build --results/--log args...]
    BENCH_MUTATED=""
    local state=$1 desc=$2
    shift 2

    if [ "$KIND" = baseline ]; then
        "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state "$state" \
            --description "$desc" \
            || abort "could not post the final status for $SHA"
        [ -n "$POST_ROLLBACK_UNHEALTHY" ] \
            && write_disabled "baseline slot's post-rollback smoke failed -- board may be unhealthy; timer disabled"
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

    local body="$RUN_DIR/report-body.md" posted=""
    if "$PY" "$TOOLS/pipeline/report.py" build \
        --map "$PIPELINE_DRIVER/local/device-identity.md" --limit 60000 \
        --verdict "$verdict" --delta "$delta" "$@" > "$body"; then
        local check_rc=0 check_err=""
        # Swaps stdout/stderr so check_err captures check's reason, not its always-empty stdout.
        check_err=$("$PY" "$TOOLS/pipeline/report.py" check \
            --map "$PIPELINE_DRIVER/local/device-identity.md" < "$body" 2>&1 >/dev/null) || check_rc=$?
        if [ "$check_rc" -eq 0 ]; then
            "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state "$state" \
                --description "$desc" --pr "$PR_NUMBER" --body "$body" && posted=1
        else
            "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state "$state" \
                --description "report withheld: $check_err" && posted=1
        fi
    else
        "$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state "$state" \
            --description "$desc" && posted=1
    fi
    [ -n "$posted" ] || abort "could not post the final status for $SHA"
    if [ -n "$POST_ROLLBACK_UNHEALTHY" ]; then
        write_disabled "baseline slot's post-rollback smoke failed -- board may be unhealthy; timer disabled"
    fi
    exit 0
}

# --- usage: resolve KIND, SHA, PR_NUMBER --------------------------------

git -C "$PIPELINE_TREE" fetch origin \
    || abort "git fetch origin failed in $PIPELINE_TREE"

case "${1:-}" in
    "")
        job=$("$PY" "$TOOLS/pipeline/candidates.py") || abort "candidates.py failed"
        if [ -z "$job" ]; then
            echo "run.sh: no candidate job" >&2
            exit 0
        fi
        # shellcheck disable=SC2086
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
        IS_CROSS=$(gh pr view "$PR_NUMBER" --json isCrossRepository --jq .isCrossRepository)
        if [ "$IS_CROSS" != "false" ]; then
            echo "run.sh: PR #$PR_NUMBER's head is in another repository -- refusing" >&2
            exit 2
        fi
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
if [ "$KIND" = pr ] \
    && [ "$(git -C "$PIPELINE_TREE" diff --name-only "$MERGE_BASE..$SHA" \
        | grep -cE '^(includes/base\.yaml|includes/platforms/|meta-wisekiosk/recipes-bsp/)')" -gt 0 ]; then
    BOOT_CAVEAT="rootfs only -- /boot unproven (issue #104 OTA does not carry /boot)"
fi

BENCH_ADDR=$("$PY" "$TOOLS/pipeline/resolve-role.py" \
    --map "$PIPELINE_DRIVER/local/device-identity.md" bench) \
    || abort "resolve-role.py refused to resolve bench"
SSH_HOST="root@$BENCH_ADDR"

RUN_DIR="$PIPELINE_DRIVER/local/pipeline/runs/$SHA"
mkdir -p "$RUN_DIR"

# --- pre-checks (before any status is posted) ---------------------------

ssh "${SSH_OPTS[@]}" "$SSH_HOST" true || abort "bench ($SSH_HOST) unreachable"

OBSERVED_HOSTNAME=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" hostname 2>/dev/null || true)
"$PY" "$TOOLS/pipeline/resolve-role.py" --map "$PIPELINE_DRIVER/local/device-identity.md" \
    --verify-hostname "$OBSERVED_HOSTNAME" \
    || abort "bench's hostname does not uniquely match the map's bench.hostname row"

if [ -f "$PIPELINE_BUILD_DIR/bitbake.lock" ] \
    && ! flock -n "$PIPELINE_BUILD_DIR/bitbake.lock" -c true 2>/dev/null; then
    abort "bitbake.lock held in $PIPELINE_BUILD_DIR"
fi
if [ "$(docker ps --format '{{.Image}}' 2>/dev/null | grep -cE '^ghcr\.io/siemens/kas/kas')" -gt 0 ]; then
    abort "a kas-container is already running"
fi
git -C "$PIPELINE_TREE" rev-parse --verify -q "${BASELINE_REMOTE}^{commit}" > /dev/null \
    || abort "baseline ref $BASELINE_REMOTE does not resolve"
if [ "$KIND" = pr ]; then
    git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse --verify -q \
        "refs/tags/baseline/$MERGE_BASE" > /dev/null \
        || abort "no baseline/$MERGE_BASE tag in $PIPELINE_BUILD_DIR/buildhistory -- run a baseline for the merge-base first"
fi
git -C "$PIPELINE_TREE" checkout --detach "$SHA" > "$RUN_DIR/checkout.log" 2>&1 \
    || abort "could not check out $SHA in $PIPELINE_TREE"

SLOTS_INFO=$(rauc_slots "$SSH_HOST") || true
BASELINE_SLOT=$(booted_bootname "$SLOTS_INFO") || abort "could not read bench's booted slot"

if [ "$KIND" = pr ]; then
    BUILDINFO_SHA=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" \
        'grep "^meta-wisekiosk" /etc/buildinfo' 2>/dev/null | sed -E 's/.*:([0-9a-f]{40}).*/\1/') \
        || true
    if [ -z "$BUILDINFO_SHA" ] || ! git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse --verify -q \
        "refs/tags/baseline/$BUILDINFO_SHA" > /dev/null; then
        abort "bench not on a baseline image"
    fi
fi

# --- pending --------------------------------------------------------------

STATUS_POSTED=1
"$PY" "$TOOLS/pipeline/report.py" post --sha "$SHA" --state pending \
    --description "pipeline $KIND $(printf '%.7s' "$SHA")" || true

# --- build ------------------------------------------------------------

bitbake_stage "build" "$RUN_DIR/build.log" "${TREE_JUST[@]}" build

if [ "$KIND" = baseline ]; then
    git -C "$PIPELINE_BUILD_DIR/buildhistory" tag -f "baseline/$SHA" \
        || abort "could not tag baseline/$SHA in buildhistory"
else
    set +e
    "${TREE_JUST[@]}" artifact-diff "baseline/$MERGE_BASE" HEAD \
        --repo "$PIPELINE_BUILD_DIR/buildhistory" \
        > "$RUN_DIR/delta-raw.txt" 2> "$RUN_DIR/delta.err"
    DELTA_RC=$?
    set -e
    if [ "$DELTA_RC" -eq 1 ]; then
        finish failure "no change in image -- close as no-op"
    elif [ "$DELTA_RC" -ne 0 ]; then
        finish error "could not compute artifact delta"
    fi
fi

# --- bundle, preflight, send, install ------------------------------------

bitbake_stage "bundle" "$RUN_DIR/bundle.log" \
    "${TREE_JUST[@]}" kiosk-bundle "$CONFIG"

refresh_remote
ota_stage "preflight" "$RUN_DIR/preflight.log" \
    "${TREE_JUST[@]}" kiosk-preflight "$IMAGE" "$BUNDLE" "$SSH_HOST"
refresh_remote
ota_stage "send" "$RUN_DIR/send.log" \
    "${TREE_JUST[@]}" kiosk-send-direct "$BUNDLE" "$SSH_HOST"

BENCH_MUTATED=1
refresh_remote
ota_stage "install" "$RUN_DIR/install.log" \
    "${TREE_JUST[@]}" kiosk-install "$SSH_HOST"

# kiosk-install's rc is its trailing diagnostic's, not rauc install's.
SLOTS_INFO=$(rauc_slots "$SSH_HOST") || true
PRIMARY_AFTER_INSTALL=$(primary_bootname "$SLOTS_INFO") \
    || abort "could not read bench's primary slot after install"
if [ "$PRIMARY_AFTER_INSTALL" = "$BASELINE_SLOT" ]; then
    abort "install did not activate the new slot; bench's primary slot is still the baseline slot"
fi

# --- reboot onto the new slot ---

if ! reboot_and_wait "$SSH_HOST" "$RUN_DIR/reboot.log" 180; then
    if wait_for_boot "$SSH_HOST" "$LAST_BOOT_ID_BEFORE" 600; then
        SLOTS_INFO=$(rauc_slots "$SSH_HOST") || true
        SLOT_NOW=$(booted_bootname "$SLOTS_INFO") \
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

SLOTS_INFO=$(rauc_slots "$SSH_HOST") || true
NEW_SLOT=$(booted_bootname "$SLOTS_INFO") || abort "could not read bench's booted slot after install"
if [ "$NEW_SLOT" = "$BASELINE_SLOT" ]; then
    finish failure "new slot did not boot; RAUC fell back"
fi
BASELINE_STATUS=$(slot_status "$SLOTS_INFO" "$BASELINE_SLOT") \
    || abort "could not read the baseline slot's own status after install"
if [ "$BASELINE_STATUS" != "good" ]; then
    abort "the baseline slot is not marked good after install -- refusing to risk a rollback with no good fallback"
fi

# --- testimage, settle, render, gpu --------------------------------------

STAGE="smoke"
rm -rf "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE"
mkdir -p "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE"
export TEST_TARGET_IP="$BENCH_ADDR"
export OEQA_JSON_RESULT_DIR="/work/local/pipeline/runs/$SHA/$STAGE"
set +e
"${TREE_JUST[@]}" testimage > "$RUN_DIR/$STAGE-testimage.log" 2>&1
TESTIMAGE_RC=$?
set -e

# oeqa's results filename is not fixed.
# shellcheck disable=SC2012
RESULTS_JSON=$(ls -t "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE"/*.json 2>/dev/null | head -1 || true)

SMOKE_STATE=success
SMOKE_RESULTS_ARGS=()
SMOKE_LOGARGS=()
if [ -z "$RESULTS_JSON" ]; then
    SMOKE_STATE=error
    f=""
    while IFS= read -r f; do SMOKE_LOGARGS+=(--log "$(basename "$f")=$f"); done \
        < <(collect_failure_logs "$RUN_DIR/$STAGE-testimage.log" "$RUN_DIR")
else
    cp "$RESULTS_JSON" "$RUN_DIR/$STAGE-testresults.json"
    SMOKE_RESULTS_ARGS=(--results "pr-slot=$RUN_DIR/$STAGE-testresults.json")

    sleep 30

    set +e
    "$TOOLS/kiosk-render-check.sh" "$SSH_HOST" > "$RUN_DIR/$STAGE-render.log" 2>&1
    RENDER_RC=$?
    "$TOOLS/kiosk-gpu-check.sh" "$SSH_HOST" > "$RUN_DIR/$STAGE-gpu.log" 2>&1
    GPU_RC=$?
    set -e

    # A skipped oeqa case leaves TESTIMAGE_RC at 0.
    [ "$TESTIMAGE_RC" -eq 0 ] || SMOKE_STATE=failure
    if [ "$RENDER_RC" -eq 2 ] || [ "$GPU_RC" -eq 2 ]; then
        [ "$SMOKE_STATE" = success ] && SMOKE_STATE=error
    elif [ "$RENDER_RC" -ne 0 ] || [ "$GPU_RC" -ne 0 ]; then
        SMOKE_STATE=failure
    fi
fi

# --- kind-specific finish -------------------------------------------------

if [ "$KIND" = baseline ]; then
    if [ "$SMOKE_STATE" = success ]; then
        ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'rauc status mark-good booted' \
            || abort "mark-good failed on bench after a passing baseline smoke"
        finish success "baseline $SHA: smoke passed"
    fi
    "${TREE_JUST[@]}" kiosk-rollback "$SSH_HOST" > "$RUN_DIR/rollback.log" 2>&1 || true
    if ! reboot_and_wait "$SSH_HOST" "$RUN_DIR/rollback-reboot.log" 180; then
        abort "bench did not come back after the baseline rollback reboot"
    fi
    SLOTS_INFO=$(rauc_slots "$SSH_HOST") || true
    SLOT_BACK=$(booted_bootname "$SLOTS_INFO") \
        || abort "could not read bench's booted slot after the baseline rollback"
    if [ "$SLOT_BACK" != "$BASELINE_SLOT" ]; then
        abort "bench resting on the wrong slot after a baseline rollback"
    fi
    finish "$SMOKE_STATE" "baseline $SHA: smoke $SMOKE_STATE"
fi

"${TREE_JUST[@]}" kiosk-rollback "$SSH_HOST" > "$RUN_DIR/rollback.log" 2>&1 || true
if ! reboot_and_wait "$SSH_HOST" "$RUN_DIR/rollback-reboot.log" 180; then
    abort "bench resting on PR slot"
fi
SLOTS_INFO=$(rauc_slots "$SSH_HOST") || true
SLOT_BACK=$(booted_bootname "$SLOTS_INFO") || abort "bench resting on PR slot"
if [ "$SLOT_BACK" != "$BASELINE_SLOT" ]; then
    abort "bench resting on PR slot"
fi
BENCH_MUTATED=""

STAGE2="post-rollback"
rm -rf "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE2"
mkdir -p "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE2"
export OEQA_JSON_RESULT_DIR="/work/local/pipeline/runs/$SHA/$STAGE2"
set +e
"${TREE_JUST[@]}" testimage > "$RUN_DIR/$STAGE2-testimage.log" 2>&1
POSTRC=$?
set -e
# shellcheck disable=SC2012
RESULTS2=$(ls -t "$PIPELINE_TREE/local/pipeline/runs/$SHA/$STAGE2"/*.json 2>/dev/null | head -1 || true)
if [ -z "$RESULTS2" ]; then
    abort "post-rollback baseline smoke produced no results"
fi
cp "$RESULTS2" "$RUN_DIR/$STAGE2-testresults.json"

[ "$POSTRC" -ne 0 ] && POST_ROLLBACK_UNHEALTHY=1

finish "$SMOKE_STATE" "pr #$PR_NUMBER $SHA: smoke $SMOKE_STATE" \
    "${SMOKE_RESULTS_ARGS[@]}" "${SMOKE_LOGARGS[@]}" \
    --results "post-rollback=$RUN_DIR/$STAGE2-testresults.json"
