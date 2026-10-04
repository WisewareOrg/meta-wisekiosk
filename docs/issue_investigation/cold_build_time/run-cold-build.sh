#!/bin/bash
# Launches the cold-cache build detached, and its watcher alongside it. Returns
# immediately -- poll build/coldbuild/{run.log,run.done,watch.log}.
#
# Usage: run-cold-build.sh [--resume]
#
# Refuses unless the pipeline is idle, and refuses a non-empty
# build/coldbuild/{tmp,sstate-cache} without --resume.
set -euo pipefail
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$REPO"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RESUME=0
if [ "${1:-}" = "--resume" ]; then RESUME=1
elif [ $# -gt 0 ]; then echo "usage: run-cold-build.sh [--resume]" >&2; exit 2
fi
# The pipeline is paused by `just pipeline-off` before this runs; this is the
# refusal if a job is still in flight rather than merely scheduled off.
if systemctl --user is-active --quiet wisekiosk-pipeline.service; then
    echo "run-cold-build.sh: wisekiosk-pipeline.service is active -- refusing" >&2; exit 1
fi
PIPELINE_ENV="$HOME/.config/wisekiosk/pipeline.env"
[ -f "$PIPELINE_ENV" ] || { echo "run-cold-build.sh: $PIPELINE_ENV not found" >&2; exit 2; }
# shellcheck disable=SC1090
. "$PIPELINE_ENV"
[ -n "${PIPELINE_LOCK:-}" ] || { echo "run-cold-build.sh: PIPELINE_LOCK not set in $PIPELINE_ENV" >&2; exit 2; }
exec 9>"$PIPELINE_LOCK"
if ! flock -n 9; then echo "run-cold-build.sh: pipeline lock held -- refusing" >&2; exit 1; fi
flock -u 9
exec 9>&-
"$HERE/write-overlay.sh"
if [ "$RESUME" -eq 0 ]; then
    for d in build/coldbuild/tmp build/coldbuild/sstate-cache; do
        if [ -d "$d" ] && [ -n "$(ls -A "$d" 2>/dev/null)" ]; then
            echo "run-cold-build.sh: $d exists and is non-empty -- pass --resume, or clear it for a fresh cold run" >&2
            exit 1
        fi
    done
fi
{
    echo "commit $(git rev-parse HEAD)  date $(date -u '+%Y-%m-%dT%H:%M:%SZ')  nproc $(nproc)"
    free -m; cat /proc/swaps
    cat /proc/pressure/memory 2>/dev/null || echo "no /proc/pressure/memory"
} > build/coldbuild/host-start.txt
setsid nohup bash -c '
    tools/kas-run.sh build "kiosk-zero-w.yaml:build/coldbuild/zz-coldbuild.yaml" > build/coldbuild/run.log 2>&1
    echo $? > build/coldbuild/run.done
' > /dev/null 2>&1 &
build_pid=$!
disown
setsid nohup "$HERE/watch.sh" > build/coldbuild/watch-stdout.log 2>&1 &
disown
echo "run-cold-build.sh: launched (build pid $build_pid); watching build/coldbuild/{run.log,run.done,watch.log}"
