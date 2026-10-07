#!/usr/bin/env bash
# The one place the check-reqs invocation is spelled out; tools/ci-guards.sh
# guard 23 and `just verify` both call this, never the command directly.
#   tools/check-reqs.sh
set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 1

uv run --locked check-reqs --root docs/requirements
