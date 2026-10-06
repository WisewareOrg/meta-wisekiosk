#!/usr/bin/env bash
# run.sh -- build, OTA and smoke-test the merge-queue head, or a missing
# baseline for it.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(dirname "$HERE")"

for v in PIPELINE_DRIVER PIPELINE_TREE PIPELINE_SSH_DIR \
        PIPELINE_KEYS_DIR PIPELINE_TARGET PIPELINE_TARGET_HOSTNAME PIPELINE_LOCK \
        DL_DIR SSTATE_DIR PATH; do
    [ -n "${!v:-}" ] || { echo "run.sh: $v not set" >&2; exit 2; }
done

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

MUTATED=""
rc=0
write_disabled() {
    mkdir -p "$PIPELINE_DRIVER/local/pipeline"
    printf '%s\n%s\n' "$(date -Is)" "$1" > "$PIPELINE_DRIVER/local/pipeline/DISABLED"
    systemctl --user disable --now wisekiosk-pipeline.timer 2>/dev/null || true
}
trap 'rc=$?; [ -n "$MUTATED" ] && write_disabled "run.sh exited (rc=$rc) with the device mid-OTA"' EXIT

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

# finish STATE TEXT [report-build.py args...] -- posts the status on $SHA,
# writes the PR comment, exits 0.
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
    local comment_url
    comment_url=$(gh pr comment "$PR_NUMBER" --body-file "$RUN_DIR/body.md" | tail -n1) \
        || abort "could not post the PR comment for $SHA"
    gh api "repos/:owner/:repo/statuses/$SHA" -f state="$state" -f context=bench-pipeline \
            -f description="${text:0:140}" -f target_url="$comment_url" > /dev/null \
        || abort "could not post the status for $SHA"
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

git -C "$PIPELINE_DRIVER" fetch --quiet origin \
    || abort "git fetch origin failed in $PIPELINE_DRIVER"
if [ "$(git -C "$PIPELINE_DRIVER" rev-parse HEAD)" != "$(git -C "$PIPELINE_DRIVER" rev-parse origin/main)" ]; then
    git -C "$PIPELINE_DRIVER" checkout --quiet --detach origin/main \
        || abort "could not check out origin/main in $PIPELINE_DRIVER"
    exec "$PIPELINE_DRIVER/tools/pipeline/run.sh" "$@"
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

[ -z "${1:-}" ] || { echo "usage: run.sh" >&2; exit 2; }

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
if git -C "$PIPELINE_BUILD_DIR/buildhistory" rev-parse --verify -q \
        "refs/tags/baseline/$BASELINE" > /dev/null 2>&1; then
    KIND=queue; SHA=$QUEUE_SHA
else
    KIND=baseline; SHA=$BASELINE
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

rm -rf "$PIPELINE_TREE/local/pipeline/runs/$SHA/smoke"
mkdir -p "$PIPELINE_TREE/local/pipeline/runs/$SHA/smoke"
export TEST_TARGET_IP="$PIPELINE_TARGET"
export OEQA_JSON_RESULT_DIR="/work/local/pipeline/runs/$SHA/smoke"

TESTIMAGE_RC=0
"${TREE_JUST[@]}" testimage > "$RUN_DIR/testimage.log" 2>&1 || TESTIMAGE_RC=$?

RESULTS_JSON="$PIPELINE_TREE/local/pipeline/runs/$SHA/smoke/testresults.json"
RESULTSARG=()
LOGARGS=()
if [ -f "$RESULTS_JSON" ]; then
    cp "$RESULTS_JSON" "$RUN_DIR/testresults.json"
    RESULTSARG=(--results "$RUN_DIR/testresults.json")
else
    stage_logargs testimage "$RUN_DIR/testimage.log"
fi

RENDER_RC=0
"$CHECKS/kiosk-render-check.sh" "$SSH_HOST" > "$RUN_DIR/render.log" 2>&1 || RENDER_RC=$?
GPU_RC=0
"$CHECKS/kiosk-gpu-check.sh" "$SSH_HOST" > "$RUN_DIR/gpu.log" 2>&1 || GPU_RC=$?
if [ "$RENDER_RC" -ne 0 ]; then
    tail -n 200 "$RUN_DIR/render.log" > "$RUN_DIR/render.tail.log"
    LOGARGS+=(--log "$RUN_DIR/render.tail.log")
fi
if [ "$GPU_RC" -ne 0 ]; then
    tail -n 200 "$RUN_DIR/gpu.log" > "$RUN_DIR/gpu.tail.log"
    LOGARGS+=(--log "$RUN_DIR/gpu.tail.log")
fi

if [ "$TESTIMAGE_RC" -eq 0 ] && [ "$RENDER_RC" -eq 0 ] && [ "$GPU_RC" -eq 0 ]; then
    SMOKE_STATE=success
else
    SMOKE_STATE=failure
fi

"${TREE_JUST[@]}" kiosk-rollback > "$RUN_DIR/rollback.log" 2>&1 \
    || abort "could not mark the booted slot bad"
"${TREE_JUST[@]}" kiosk-reboot > "$RUN_DIR/rollback-reboot.log" 2>&1 \
    || abort "device did not come back after the rollback reboot"
SLOT_NOW=$(booted_slot "$SSH_HOST") || abort "could not read the booted slot after the rollback"
[ "$SLOT_NOW" = "$PREV_SLOT" ] || abort "device resting on the job's slot"

[ "$SMOKE_STATE" = success ] && tag_job_baseline

finish "$SMOKE_STATE" "pr #$PR_NUMBER $SHA: smoke $SMOKE_STATE" \
    "${RESULTSARG[@]}" "${LOGARGS[@]}"
