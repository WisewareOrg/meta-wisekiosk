#!/bin/bash
# trigger-138d914-build.sh -- waits for smoothness to finish inside orchestrate-tonight.log
# (the soak-starting line, printed only after all 3 smoothness runs), then builds exactly
# 138d914 in the dedicated worktree (-185-254, separate from -185 which stays on d97d6fe) --
# local/host-only, no lock, no device contact, so it can run alongside the soak.
set -u
LOGDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs
TONIGHT_LOG="$LOGDIR/orchestrate-tonight.log"
BUILD_LOG="$LOGDIR/build-138d914-tonight.log"

echo "--- waiting for smoothness to finish (soak starting) ---"
until grep -q "=== soak starting" "$TONIGHT_LOG" 2>/dev/null; do sleep 10; done
echo "smoothness done, soak starting -- building 138d914 now"

cd /home/tjwise/meta-wisekiosk-185-254
git fetch origin 185-wpe-2.54 >&2
git checkout 138d9142b2cff9c59cd0a755595bc3a82db7e3e3 >&2
git status --short >&2

rm -f "$BUILD_LOG" "$BUILD_LOG.done"
export DL_DIR=/home/tjwise/meta-wisekiosk/build/downloads
export SSTATE_DIR=/home/tjwise/meta-wisekiosk/build/sstate-cache
export PIPELINE_KEYS_DIR=/home/tjwise/meta-wisekiosk/local/keys
just build > "$BUILD_LOG" 2>&1
rc=$?
echo "BUILD_EXIT=$rc" >> "$BUILD_LOG"
touch "$BUILD_LOG.done"
echo "TRIGGER_138D914_BUILD_DONE rc=$rc"
