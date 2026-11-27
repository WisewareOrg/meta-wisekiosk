#!/usr/bin/env bash
# PreCompact -- fires before the context is summarized.
#
# Reports uncommitted changes, worktrees and a running kas build, writes the full
# report to a snapshot file and prints a one-line systemMessage pointing at it.
# Never blocks; every external call is bounded by `timeout`.
set -uo pipefail

payload=$(cat 2>/dev/null)
trigger=$(printf '%s' "$payload" | jq -r '.trigger // "unknown"' 2>/dev/null) || trigger=unknown
[ -n "$trigger" ] || trigger=unknown

REPO=${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}

out=""
add() { out="${out}${1}
"; }

add "COMPACTION (${trigger}). The repository is the durable state; this context is not."
add ""

dirty_total=0
if git -C "$REPO" rev-parse --git-dir > /dev/null 2>&1; then
    br=$(timeout 5 git -C "$REPO" symbolic-ref --short HEAD 2>/dev/null || echo '(detached)')
    sha=$(timeout 5 git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')
    dirty=$(timeout 10 git -C "$REPO" status --short 2>/dev/null)
    if [ -n "$dirty" ]; then
        dirty_total=$(printf '%s\n' "$dirty" | wc -l)
        add "UNCOMMITTED -- compaction will NOT preserve this: $REPO ($br @ $sha)"
        add "$(printf '%s\n' "$dirty" | sed 's/^/    /')"
    else
        add "clean: $REPO ($br @ $sha)"
    fi

    wt=$(timeout 5 git -C "$REPO" worktree list 2>/dev/null | tail -n +2)
    [ -n "$wt" ] && { add ""; add "worktrees in play:"; add "$(printf '%s\n' "$wt" | sed 's/^/    /')"; }
else
    add "NOT A GIT CHECKOUT: $REPO -- nothing here can report what is uncommitted."
fi

# A running kas container: the build tree must not be edited (guard.sh rule 8).
builds=$(timeout 5 docker ps --format '{{.Names}} {{.Status}} {{.Image}}' 2>/dev/null | grep -i kas)
[ -n "$builds" ] && { add ""; add "BUILD RUNNING (do not edit the build tree):"; add "    $builds"; }

add ""
add "Where the state lives, in reading order:"
add "    README.md                       what this repository is, and the index of every document"
add "    CLAUDE.md                       the agent working rules"
add "    CONTRIBUTING.md                 the gates, the conventions, and the review checklist"
add "    local/                          gitignored operator notes, keys, raw captures"
add ""
add "Before relying on the summary: anything above marked UNCOMMITTED is a finding"
add "that exists only in the context being discarded. Write it down first."

# PreCompact output accepts only continue / suppressOutput / systemMessage;
# hookSpecificOutput.additionalContext fails schema validation for this event.
snapshot="${HOME}/.claude/precompact-snapshot-meta-wisekiosk.md"
mkdir -p "$(dirname "$snapshot")" 2>/dev/null
printf '%s\n' "$out" > "$snapshot" 2>/dev/null

if [ "$dirty_total" -gt 0 ]; then
    msg="Compacting with ${dirty_total} uncommitted change(s) in meta-wisekiosk -- findings not yet on disk will be lost. Full pre-compaction snapshot written to ${snapshot} -- read it if the summary looks thin."
else
    msg="Compacting; meta-wisekiosk is clean, state is on disk. Pre-compaction snapshot: ${snapshot}."
fi

jq -nc --arg m "$msg" '{systemMessage:$m}' 2>/dev/null || printf '%s\n' "$msg"
