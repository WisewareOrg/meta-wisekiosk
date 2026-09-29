#!/usr/bin/env bash
# Grant this session time-boxed authorization to run a fixed set of
# destructive operations against the PROD board. .claude/hooks/guard.sh RULE 1
# is the only consumer of the file this writes: under a valid grant it allows
# an OTA, install, reboot, rollback or reprovision of prod; everything else
# (flash, bootprofile, rauc-rotate, poweroff/halt/shutdown/kexec) stays
# blocked regardless. Revoke when the work the grant was for is done.
#
#   tools/prod-authorize.sh [--hours H]   -- grant H hours (integer 1-12, default 12)
#   tools/prod-authorize.sh --show        -- print the current grant, if any
#   tools/prod-authorize.sh --revoke      -- remove the grant
#
# This does not gate itself -- nothing stops a session from running this on
# its own authority. The gate is the human who approved the session running
# it; the grant only bounds its SCOPE and its EXPIRY once that trust is given.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# Resolved exactly as guard.sh resolves KIOSK_IDENTITY_FILE: local/ is
# gitignored, so it exists in the PRIMARY worktree only, and a linked worktree
# must still land (and look for) the grant there, not beside itself.
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
    if [ -L "$PAFILE" ]; then
        echo "no grant -- $PAFILE is a symlink, never trusted" >&2
        exit 1
    fi
    if [ ! -f "$PAFILE" ]; then
        echo "no grant"
        exit 1
    fi
    content=$(cat "$PAFILE")
    case "$content" in
        expires=*) exp=${content#expires=} ;;
        *) exp= ;;
    esac
    case "$exp" in
        ''|*[!0-9]*)
            echo "no grant -- $PAFILE is malformed"
            exit 1
            ;;
    esac
    if [ "$exp" -gt "$(date +%s)" ]; then
        echo "granted until $(date -d "@$exp")"
    else
        echo "no grant -- expired $(date -d "@$exp")"
        exit 1
    fi
    ;;
revoke)
    rm -f "$PAFILE"
    echo "revoked"
    ;;
grant)
    case "$HOURS" in
        ''|*[!0-9]*)
            echo "--hours must be an integer from 1 to 12" >&2; exit 2 ;;
    esac
    if [ "$HOURS" -lt 1 ] || [ "$HOURS" -gt 12 ]; then
        echo "--hours must be an integer from 1 to 12" >&2; exit 2
    fi
    mkdir -p "$(dirname "$PAFILE")"
    expires=$(( $(date +%s) + HOURS * 3600 ))
    printf 'expires=%s\n' "$expires" > "$PAFILE"
    echo "granted until $(date -d "@$expires") ($PAFILE)"
    ;;
esac
