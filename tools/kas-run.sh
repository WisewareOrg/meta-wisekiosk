#!/usr/bin/env bash
# Runs the build-input writers, then execs kas-container with the given args.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: tools/kas-run.sh [--help] <kas-container args...>

Environment:
  PIPELINE_KEYS_DIR   mounted read-only at /work/local/keys; no whitespace
  PIPELINE_HASHSERV   path to the shared hashserv unix socket; its directory
                      (which holds only the socket) is bind-mounted at
                      /run/wisekiosk-hashserv and BB_HASHSERVE is set to the
                      socket's path there; no whitespace
  KAS_RUN_ENV         space-separated variable NAMES passed through to
                      kas-container as -e NAME, for each that is non-empty

Refuses --runtime-args and --docker-args in <kas-container args...>.

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

if [[ "${PIPELINE_HASHSERV:-}" == *[[:space:]]* ]]; then
    echo "tools/kas-run.sh: PIPELINE_HASHSERV must not contain whitespace" >&2
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
if [ -n "${PIPELINE_HASHSERV:-}" ]; then
    hashserv_dir="$(dirname "$PIPELINE_HASHSERV")"
    hashserv_sock="/run/wisekiosk-hashserv/$(basename "$PIPELINE_HASHSERV")"
    runtime="$runtime -v $hashserv_dir:/run/wisekiosk-hashserv -e BB_HASHSERVE=unix://$hashserv_sock"
fi
if [ -n "${KAS_RUN_ENV:-}" ]; then
    for name in $KAS_RUN_ENV; do
        if [ -n "${!name:-}" ]; then
            runtime="$runtime -e $name"
        fi
    done
fi

exec kas-container ${runtime:+--runtime-args "$runtime"} "$@"
