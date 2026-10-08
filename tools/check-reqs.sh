#!/usr/bin/env bash
# The one place the check-reqs invocation is spelled out; tools/ci-guards.sh
# guard 23 and `just verify` both call this, never the command directly.
#   tools/check-reqs.sh
set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 1

# Doorstop walks from the project root; build/ and sources/ are gitignored and
# skipped by a marker the gate writes once each directory exists.
for dir in build sources; do
    [ -d "$dir" ] && [ ! -f "$dir/.doorstop.skip-all" ] && : > "$dir/.doorstop.skip-all"
done

uv run --locked check-reqs --root docs/requirements
