#!/usr/bin/env bash
# Runs the build-input writers, then execs kas-container with the given args.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: tools/kas-run.sh [--help] <kas-container args...>

Mounts $HOME/.local/share/bitbake-hashserv read-only at /hashserv; refuses to
run if that directory is missing.

Takes an exclusive lock on $HOME/.local/share/bitbake-hashserv/kas-build.lock
for as long as kas-container runs, so one kas build at a time runs on this host;
a second waits and says which
build (the pid and checkout in the lock file) holds it. An interactive shell (`shell` with none of -c, --cmd or
--command) does not take it.

Environment:
  PIPELINE_KEYS_DIR   mounted read-only at /work/local/keys; no whitespace
  KAS_RUN_TMP_DIR     mounted read-write at the same path inside the container; no
                      whitespace
  KAS_RUN_ENV         space-separated variable NAMES passed through to
                      kas-container as -e NAME, for each that is non-empty

Refuses --runtime-args and --docker-args in <kas-container args...>.

Exits with kas-container's status, a failing writer's status, 1 if the
bitbake-hashserv data directory is missing, or 2 on bad usage.
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
        echo "tools/kas-run.sh: $arg not allowed; set PIPELINE_KEYS_DIR, KAS_RUN_TMP_DIR or KAS_RUN_ENV instead" >&2
        exit 2
    fi
done

if [[ "${PIPELINE_KEYS_DIR:-}" == *[[:space:]]* ]]; then
    echo "tools/kas-run.sh: PIPELINE_KEYS_DIR must not contain whitespace" >&2
    exit 2
fi

if [[ "${KAS_RUN_TMP_DIR:-}" == *[[:space:]]* ]]; then
    echo "tools/kas-run.sh: KAS_RUN_TMP_DIR must not contain whitespace" >&2
    exit 2
fi

cd "$(dirname "$0")/.."

HASHSERV_DIR="$HOME/.local/share/bitbake-hashserv"
if [ ! -d "$HASHSERV_DIR" ]; then
    echo 'tools/kas-run.sh: bitbake-hashserv data directory missing: see README.md §"Quick start"' >&2
    exit 1
fi

case "${1:-}" in
    shell)
        interactive=1
        for arg in "$@"; do
            case "$arg" in
                -c|--cmd|--command) interactive=0 ;;
            esac
        done
        ;;
    *) interactive=0 ;;
esac
if [ "$interactive" -eq 0 ]; then
    if [ -n "${KAS_RUN_LOCKED:-}" ]; then
        echo "tools/kas-run.sh: called from a kas-run.sh that holds the build lock (nested): refusing, it would wait for itself" >&2
        exit 2
    fi
    lock="$HASHSERV_DIR/kas-build.lock"
    exec 9>>"$lock"
    flock -n 9 || { echo "kas-run: waiting for another kas build on this host: $(cat "$lock")" >&2; flock 9; }
    printf '%s %s\n' "$$" "$PWD" > "$lock"
    export KAS_RUN_LOCKED=1
fi

py="${py:-python3}"
tools/write-build-rev.sh
"$py" tools/go-mods.py
"$py" tools/app-lockfile.py

runtime="-v $HASHSERV_DIR:/hashserv:ro"
if [ -n "${PIPELINE_KEYS_DIR:-}" ]; then
    runtime="$runtime -v $PIPELINE_KEYS_DIR:/work/local/keys:ro"
fi
if [ -n "${KAS_RUN_TMP_DIR:-}" ]; then
    runtime="$runtime -v $KAS_RUN_TMP_DIR:$KAS_RUN_TMP_DIR"
fi
if [ -n "${KAS_RUN_ENV:-}" ]; then
    for name in $KAS_RUN_ENV; do
        if [ -n "${!name:-}" ]; then
            runtime="$runtime -e $name"
        fi
    done
fi

exec kas-container ${runtime:+--runtime-args "$runtime"} "$@"
