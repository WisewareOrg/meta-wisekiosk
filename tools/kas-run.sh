#!/usr/bin/env bash
# Runs the build-input writers, then execs kas-container with the given args.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: tools/kas-run.sh [--help] <kas-container args...>

Environment:
  PIPELINE_KEYS_DIR   mounted read-only at /work/local/keys
  KAS_RUN_ENV         space-separated variable NAMES passed through to
                      kas-container as -e NAME=value, for each that is non-empty

Exits with kas-container's status, a failing writer's status, or 2 on bad usage.
EOF
}

if [ "${1:-}" = "--help" ]; then
    usage
    exit 0
fi

if [ $# -eq 0 ]; then
    usage >&2
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
            runtime="$runtime -e $name=${!name}"
        fi
    done
fi

exec kas-container ${runtime:+--runtime-args "$runtime"} "$@"
