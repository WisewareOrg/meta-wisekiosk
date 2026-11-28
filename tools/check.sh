#!/usr/bin/env bash
# Run the repository checks, each one even after an earlier one fails, and name the ones that failed.
#
#   tools/check.sh [--allow-partial] [--image]
#
# Checks, in order: pytest over tests/prechecks and the screenshot decoder test,
# tools/doc-links.py, tools/scrub-identity.py --check, wise-ci's check-reqs over docs/requirements,
# and check-adrs. --allow-partial is passed to the identity scan, for a clone that lacks
# local/device-identity.md. --image adds tools/doc-image.py, which reads the image build/ holds. The
# interpreter is $py, which just exports, else the repo .venv's python3 when present.
#
# Exit: 0 every check passed; 1 at least one failed; 2 an unknown flag.
set -uo pipefail

usage() {
    echo "usage: check.sh [--allow-partial] [--image]" >&2
    exit 2
}

scrub=(--check)
image=0
for arg in "$@"; do
    case "$arg" in
        --allow-partial) scrub+=(--allow-partial) ;;
        --image) image=1 ;;
        *) usage ;;
    esac
done

cd "$(dirname "$0")/.." || exit 1
if [ -z "${py:-}" ]; then
    py=python3
    [ -x .venv/bin/python3 ] && py=.venv/bin/python3
fi
failed=()

run() {
    local name=$1
    shift
    "$@" || failed+=("$name")
}

run prechecks "$py" -m pytest tests/prechecks tests/applications/screenshot/test_decoder.py
run doc-links "$py" tools/doc-links.py
run scrub-identity "$py" tools/scrub-identity.py "${scrub[@]}"
run check-reqs uv run --locked check-reqs --root docs/requirements
run check-adrs uv run --locked check-adrs
if [ "$image" -eq 1 ]; then
    run doc-image "$py" tools/doc-image.py check
fi

if [ "${#failed[@]}" -gt 0 ]; then
    echo
    echo "FAILED: ${failed[*]}"
    exit 1
fi
echo
echo "all checks passed"
