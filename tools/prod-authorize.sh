#!/usr/bin/env bash
# Write a time-boxed grant file. .claude/hooks/guard.sh RULE 1 is its only consumer: under a valid
# grant it allows an OTA, install, reboot, rollback or reprovision of prod; flash, rauc-rotate and
# poweroff/halt/shutdown/kexec stay blocked.
#
#   tools/prod-authorize.sh [--hours H]   -- grant H hours (integer 1-12, default 12)
#   tools/prod-authorize.sh --show        -- print the grant file's raw contents, if any
#   tools/prod-authorize.sh --revoke      -- remove the grant
#
# --show gives no verdict; .claude/hooks/guard.sh decides whether a grant is valid. The grant
# bounds scope and expiry and does not authenticate the caller.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# Resolved as guard.sh resolves KIOSK_IDENTITY_FILE: a linked worktree uses the primary worktree's local/.
PAFILE=${KIOSK_PROD_AUTH_FILE:-}
if [ -z "$PAFILE" ]; then
    PAFILE=$REPO/local/prod-auth
    if [ ! -f "$PAFILE" ]; then
        gitcommon=$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null)
        if [ -n "$gitcommon" ]; then
            case "$gitcommon" in /*) ;; *) gitcommon=$REPO/$gitcommon ;; esac
            primary=$(cd "$gitcommon/.." 2>/dev/null && pwd)
            [ -n "$primary" ] && PAFILE=$primary/local/prod-auth
        fi
    fi
fi

HOURS=12
ACTION=grant
while [ $# -gt 0 ]; do
    case "$1" in
        --hours) HOURS=${2:?--hours needs a value}; shift 2 ;;
        --show)  ACTION=show; shift ;;
        --revoke) ACTION=revoke; shift ;;
        *) echo "usage: prod-authorize.sh [--hours H] | --show | --revoke" >&2; exit 2 ;;
    esac
done

case "$ACTION" in
show)
    # Prints the path and the raw content, uninterpreted.
    if [ ! -e "$PAFILE" ]; then
        echo "no grant file at $PAFILE"
        exit 1
    fi
    echo "$PAFILE:"
    cat "$PAFILE"
    ;;
revoke)
    if [ -e "$PAFILE" ] || [ -L "$PAFILE" ]; then
        rm -f "$PAFILE"
        echo "revoked $PAFILE"
    else
        echo "no grant to revoke at $PAFILE"
    fi
    ;;
grant)
    case "$HOURS" in
        ''|*[!0-9]*)
            echo "--hours must be an integer from 1 to 12" >&2; exit 2 ;;
    esac
    # Base 10: bash arithmetic reads a leading 0 as octal.
    HOURS=$((10#$HOURS))
    if [ "$HOURS" -lt 1 ] || [ "$HOURS" -gt 12 ]; then
        echo "--hours must be an integer from 1 to 12" >&2; exit 2
    fi
    # guard.sh's grant_valid() rejects a symlinked grant.
    if [ -L "$PAFILE" ]; then
        echo "refusing to write through a symlink at $PAFILE" >&2
        exit 1
    fi
    mkdir -p "$(dirname "$PAFILE")"
    expires=$(( $(date +%s) + HOURS * 3600 ))
    printf 'expires=%s\n' "$expires" > "$PAFILE"
    echo "granted until $(date -d "@$expires") ($PAFILE)"
    ;;
esac
