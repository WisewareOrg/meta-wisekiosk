#!/bin/bash
# check-cog-cache-resolver.sh <ssh-target> -- read-only: the cache dir cog-cache.sh resolves on
# the board and its entry count. Deletes nothing.
set -u
T=${1:?ssh-target}
HERE=$(dirname "$(readlink -f "$0")")
KSSH=$(git -C "$HERE" rev-parse --show-toplevel)/tools/kiosk-ssh.sh
# shellcheck source-path=SCRIPTDIR source=cog-cache.sh
. "$HERE/cog-cache.sh"
echo "# check-cog-cache-resolver.sh harness $(git -C "$HERE" rev-parse HEAD)$(git -C "$HERE" diff --quiet HEAD -- . || echo " DIRTY")"
{ printf '%s\n' "$COG_CACHE_FN"; cat <<'REMOTE'; } | "$KSSH" "$T" 'sh -s'
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# cog pid $(pidof cog)"
c=$(cog_cache_dir)
echo "resolved $c"
if [ -d "$c" ]; then echo "entries $(($(find "$c" | wc -l) - 1))"; else echo "absent"; fi
REMOTE
