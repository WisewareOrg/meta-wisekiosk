#!/usr/bin/env bash
# The device pipeline's stage driver.
#
#   run.sh                  -- build & OTA the head of the merge queue, or a
#                              missing baseline for it
#   run.sh baseline [<sha>] -- build & OTA a baseline run (default sha:
#                              $PIPELINE_BASELINE_REF's current HEAD)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(dirname "$HERE")"

for v in PIPELINE_DRIVER PIPELINE_TREE PIPELINE_BASELINE_REF PIPELINE_SSH_DIR \
        PIPELINE_KEYS_DIR PIPELINE_TARGET PIPELINE_TARGET_HOSTNAME DL_DIR \
        SSTATE_DIR PATH; do
    [ -n "${!v:-}" ] || { echo "run.sh: $v not set" >&2; exit 2; }
done
export DL_DIR SSTATE_DIR PIPELINE_SSH_DIR PIPELINE_KEYS_DIR

LOCK="$HOME/.config/wisekiosk/pipeline.lock"
mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
flock -n 9 || { echo "run.sh: pipeline lock held -- another run in progress" >&2; exit 0; }

unset KAS_BUILD_DIR
PIPELINE_BUILD_DIR="$PIPELINE_TREE/build"
PY=python3; [ -x "$PIPELINE_DRIVER/.venv/bin/python3" ] && PY="$PIPELINE_DRIVER/.venv/bin/python3"
TREE_JUST=(just --justfile "$PIPELINE_TREE/Justfile" --working-directory "$PIPELINE_TREE")
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
CONFIG="kiosk-zero-w.yaml"
MACHINE_DIR="raspberrypi0-wifi"
IMAGE="$PIPELINE_BUILD_DIR/tmp-$MACHINE_DIR/deploy/images/$MACHINE_DIR/core-image-base-$MACHINE_DIR.rootfs.ext4"
BUNDLE="$PIPELINE_BUILD_DIR/tmp-$MACHINE_DIR/deploy/images/$MACHINE_DIR/update-bundle-$MACHINE_DIR.raucb"
SSH_HOST="root@$PIPELINE_TARGET"

MUTATED=""
write_disabled() {
    mkdir -p "$PIPELINE_DRIVER/local/pipeline"
    printf '%s\n%s\n' "$(date -Is)" "$1" > "$PIPELINE_DRIVER/local/pipeline/DISABLED"
    systemctl --user disable --now wisekiosk-pipeline.timer 2>/dev/null || true
}
trap '[ -n "$MUTATED" ] && write_disabled "run.sh exited (rc=$?) with the device mid-OTA"' EXIT

abort() {
    MUTATED=""
    write_disabled "$1"
    echo "run.sh: ABORTED -- $1" >&2
    exit 1
}

# booted_slot HOST -- the currently booted slot's bootname.
booted_slot() {
    ssh "${SSH_OPTS[@]}" "$1" '
        eval "$(rauc status --output-format=shell)"
        for i in $RAUC_SLOTS; do
            eval s=\$RAUC_SLOT_STATE_$i
            eval b=\$RAUC_SLOT_BOOTNAME_$i
            [ "$s" = booted ] && { echo "$b"; exit 0; }
        done
        exit 1
    '
}

# failure_logs BUILD_LOG OUT_DIR -- tails each bitbake failure log named in
# BUILD_LOG into OUT_DIR, translating the container's /work/ prefix; prints
# one path per copy.
failure_logs() {
    local buildlog=$1 outdir=$2 n=0 path hostpath
    while IFS= read -r path; do
        hostpath=$path
        case "$hostpath" in
            /work/*) hostpath="$PIPELINE_TREE/${hostpath#/work/}" ;;
        esac
        n=$((n + 1))
        tail -n 200 "$hostpath" > "$outdir/failure-$n.log" 2>/dev/null \
            || echo "(could not read $path)" > "$outdir/failure-$n.log"
        echo "$outdir/failure-$n.log"
    done < <(grep -oE 'Logfile of failure stored in: .*' "$buildlog" 2>/dev/null \
            | sed 's/^Logfile of failure stored in: //')
}

# finish STATE TEXT [report-build.py args...] -- posts the status on $SHA,
# writes the PR comment, exits 0.
finish() {
    MUTATED=""
    local state=$1 text=$2; shift 2
    printf 'pr #%s  sha: %s  baseline: %s\nVERDICT: %s\n' \
        "$PR_NUMBER" "$SHA" "$BASELINE" "$text" > "$RUN_DIR/verdict.txt"
    "$PY" "$TOOLS/pipeline/report-build.py" --verdict "$RUN_DIR/verdict.txt" \
            --delta "$RUN_DIR/delta.txt" "$@" \
        | "$TOOLS/scrub-identity.py" --filter "$PIPELINE_DRIVER" \
        | head -c 60000 > "$RUN_DIR/body.md" \
        || abort "could not assemble the report body for $SHA"
    local comment_url
    comment_url=$(gh pr comment "$PR_NUMBER" --body-file "$RUN_DIR/body.md" | tail -n1) \
        || abort "could not post the PR comment for $SHA"
    gh api "repos/:owner/:repo/statuses/$SHA" -f state="$state" -f context=bench-pipeline \
            -f description="${text:0:140}" -f target_url="$comment_url" > /dev/null \
        || abort "could not post the status for $SHA"
    exit 0
}

# collect_logargs LOGFILE -- fills LOGARGS with --log NAME=PATH per failure
# log LOGFILE names.
collect_logargs() {
    LOGARGS=()
    local f
    while IFS= read -r f; do LOGARGS+=(--log "$(basename "$f")=$f"); done \
        < <(failure_logs "$1" "$RUN_DIR")
}

# run_or_fail NAME LOGFILE cmd... -- on failure, finishes "NAME failed" with
# any bitbake failure-task logs attached.
run_or_fail() {
    local name=$1 log=$2; shift 2
    "$@" > "$log" 2>&1 && return 0
    collect_logargs "$log"
    finish failure "$name failed" "${LOGARGS[@]}"
}

git -C "$PIPELINE_TREE" fetch origin || abort "git fetch origin failed in $PIPELINE_TREE"

case "${1:-}" in
    "")
        QUEUE_REFS=$(git ls-remote origin 'refs/heads/gh-readonly-queue/main/*') \
            || abort "git ls-remote for the merge queue failed"
        if [ -z "$QUEUE_REFS" ]; then
            echo "run.sh: no job" >&2
            exit 0
        fi
        CURRENT_MAIN=$(git -C "$PIPELINE_TREE" rev-parse origin/main) || abort "could not resolve origin/main"
        MATCHING=$(printf '%s\n' "$QUEUE_REFS" | while IFS="$(printf '\t')" read -r sha ref; do
            base=$(printf '%s' "$ref" | sed -nE 's#^refs/heads/gh-readonly-queue/main/pr-[0-9]+-([0-9a-f]+)$#\1#p')
            [ "$base" = "$CURRENT_MAIN" ] && printf '%s\t%s\n' "$sha" "$ref"
        done)
        MATCH_COUNT=$(printf '%s\n' "$MATCHING" | grep -c . || true)
        if [ "$MATCH_COUNT" -eq 0 ]; then
            echo "run.sh: no job" >&2
            exit 0
        elif [ "$MATCH_COUNT" -gt 1 ]; then
            echo "run.sh: more than one gh-readonly-queue ref based on origin/main" >&2
            exit 2
        fi
        QUEUE_SHA=$(printf '%s' "$MATCHING" | cut -f1)
        QUEUE_REF=$(printf '%s' "$MATCHING" | cut -f2)
        PR_NUMBER=$(printf '%s' "$QUEUE_REF" | sed -nE 's#^refs/heads/gh-readonly-queue/main/pr-([0-9]+)-.*#\1#p')
        [ -n "$PR_NUMBER" ] || abort "could not parse a PR number from $QUEUE_REF"
        git -C "$PIPELINE_TREE" fetch --quiet origin "$QUEUE_REF" || abort "could not fetch $QUEUE_REF"
        BASELINE=$(git -C "$PIPELINE_TREE" rev-parse "$QUEUE_SHA^1") || abort "could not resolve $QUEUE_SHA^1"
        if git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse --verify -q \
                "refs/tags/baseline/$BASELINE" > /dev/null 2>&1; then
            KIND=queue; SHA=$QUEUE_SHA
        else
            KIND=baseline; SHA=$BASELINE
        fi
        ;;
    baseline)
        KIND=baseline
        SHA=${2:-$(git -C "$PIPELINE_TREE" rev-parse "$PIPELINE_BASELINE_REF")}
        ;;
    *)
        echo "usage: run.sh | run.sh baseline [<sha>]" >&2
        exit 2
        ;;
esac

RUN_DIR="$PIPELINE_DRIVER/local/pipeline/runs/$SHA"
mkdir -p "$RUN_DIR"

if [ "$KIND" = baseline ]; then
    git -C "$PIPELINE_TREE" checkout --detach "$SHA" > "$RUN_DIR/checkout.log" 2>&1 \
        || abort "could not check out $SHA in $PIPELINE_TREE"
    "${TREE_JUST[@]}" build > "$RUN_DIR/build.log" 2>&1 || abort "baseline build failed"
    git -C "$PIPELINE_BUILD_DIR/buildhistory" tag -f "baseline/$SHA" \
        || abort "could not tag baseline/$SHA"
    exit 0
fi

OBSERVED_HOSTNAME=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" hostname 2>/dev/null || true)
[ "$OBSERVED_HOSTNAME" = "$PIPELINE_TARGET_HOSTNAME" ] \
    || abort "PIPELINE_TARGET's live hostname does not match PIPELINE_TARGET_HOSTNAME"

git -C "$PIPELINE_TREE" checkout --detach "$SHA" > "$RUN_DIR/checkout.log" 2>&1 \
    || abort "could not check out $SHA in $PIPELINE_TREE"
PREV_SLOT=$(booted_slot "$SSH_HOST") || abort "could not read the booted slot before install"

run_or_fail build "$RUN_DIR/build.log" "${TREE_JUST[@]}" build

JOB_BH=$(git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse HEAD) \
    || abort "could not read the job's buildhistory commit"
set +e
"${TREE_JUST[@]}" artifact-diff "baseline/$BASELINE" "$JOB_BH" \
    > "$RUN_DIR/delta.txt" 2> "$RUN_DIR/delta.err"
DELTA_RC=$?
set -e
[ "$DELTA_RC" -eq 1 ] && finish success "no change in image; no device run"
[ "$DELTA_RC" -eq 0 ] || finish error "artifact diff could not tell"

run_or_fail bundle "$RUN_DIR/bundle.log" "${TREE_JUST[@]}" kiosk-bundle "$CONFIG"
run_or_fail preflight "$RUN_DIR/preflight.log" \
    "${TREE_JUST[@]}" kiosk-preflight "$IMAGE" "$BUNDLE" "$SSH_HOST"
run_or_fail send "$RUN_DIR/send.log" "${TREE_JUST[@]}" kiosk-send-direct "$BUNDLE" "$SSH_HOST"
MUTATED=1
run_or_fail install "$RUN_DIR/install.log" "${TREE_JUST[@]}" kiosk-install "$SSH_HOST"

DEVICE_BACK=1
"${TREE_JUST[@]}" kiosk-reboot "$SSH_HOST" timeout=180 > "$RUN_DIR/reboot.log" 2>&1 || DEVICE_BACK=0

SMOKE_STATE=error
RESULTSARG=()
LOGARGS=()
if [ "$DEVICE_BACK" -eq 1 ]; then
    rm -rf "$PIPELINE_TREE/local/pipeline/runs/$SHA/smoke"
    mkdir -p "$PIPELINE_TREE/local/pipeline/runs/$SHA/smoke"
    export TEST_TARGET_IP="$PIPELINE_TARGET"
    export OEQA_JSON_RESULT_DIR="/work/local/pipeline/runs/$SHA/smoke"
    set +e
    "${TREE_JUST[@]}" testimage > "$RUN_DIR/testimage.log" 2>&1
    TESTIMAGE_RC=$?
    set -e
    RESULTS_JSON=$(find "$PIPELINE_TREE/local/pipeline/runs/$SHA/smoke" -maxdepth 1 -name '*.json' \
            -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2- || true)
    if [ -z "$RESULTS_JSON" ]; then
        collect_logargs "$RUN_DIR/testimage.log"
    else
        cp "$RESULTS_JSON" "$RUN_DIR/testresults.json"
        RESULTSARG=(--results "$RUN_DIR/testresults.json")
        sleep 30
        set +e
        "$TOOLS/kiosk-render-check.sh" "$SSH_HOST" > "$RUN_DIR/render.log" 2>&1; RENDER_RC=$?
        "$TOOLS/kiosk-gpu-check.sh" "$SSH_HOST" > "$RUN_DIR/gpu.log" 2>&1; GPU_RC=$?
        set -e
        if [ "$TESTIMAGE_RC" -eq 0 ] && [ "$RENDER_RC" -eq 0 ] && [ "$GPU_RC" -eq 0 ]; then
            SMOKE_STATE=success
        else
            SMOKE_STATE=failure
        fi
    fi
fi

"${TREE_JUST[@]}" kiosk-rollback "$SSH_HOST" > "$RUN_DIR/rollback.log" 2>&1 \
    || abort "could not mark the booted slot bad"
"${TREE_JUST[@]}" kiosk-reboot "$SSH_HOST" > "$RUN_DIR/rollback-reboot.log" 2>&1 \
    || abort "device did not come back after the rollback reboot"
SLOT_NOW=$(booted_slot "$SSH_HOST") || abort "could not read the booted slot after the rollback"
[ "$SLOT_NOW" = "$PREV_SLOT" ] || abort "device resting on the job's slot"
MUTATED=""

if [ "$DEVICE_BACK" -eq 0 ]; then
    finish failure "new slot did not boot"
fi
finish "$SMOKE_STATE" "pr #$PR_NUMBER $SHA: smoke $SMOKE_STATE" \
    "${RESULTSARG[@]}" "${LOGARGS[@]}"
