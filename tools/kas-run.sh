#!/usr/bin/env bash
# Runs the build-input writers, then execs kas-container with the given args.
set -euo pipefail

if [ $# -eq 0 ]; then
    echo "usage: tools/kas-run.sh <kas-container args...>" >&2
    exit 2
fi

for arg in "$@"; do
    if [ "$arg" = "--runtime-args" ] || [ "$arg" = "--docker-args" ]; then
        echo "tools/kas-run.sh: $arg not allowed; set PIPELINE_KEYS_DIR or KAS_RUN_ENV instead" >&2
        exit 2
    fi
done

if [[ "${PIPELINE_KEYS_DIR:-}" == *[[:space:]]* ]]; then
    echo "tools/kas-run.sh: PIPELINE_KEYS_DIR must not contain whitespace" >&2
    exit 2
fi

cd "$(dirname "$0")/.."

py="${py:-python3}"
tools/write-build-rev.sh
"$py" tools/go-mods.py
"$py" tools/app-lockfile.py

runtime=""
if [ -n "${PIPELINE_KEYS_DIR:-}" ]; then
    runtime="-v $PIPELINE_KEYS_DIR:/work/local/keys:ro"
fi
if [ -n "${KAS_RUN_ENV:-}" ]; then
    for name in $KAS_RUN_ENV; do
        if [ -n "${!name:-}" ]; then
            runtime="$runtime -e $name"
        fi
    done
fi

exec kas-container ${runtime:+--runtime-args "$runtime"} "$@"
