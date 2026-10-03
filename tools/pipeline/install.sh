#!/usr/bin/env bash
# Provision the pipeline's checkouts, ssh key and env file.
# Env: DL_DIR (default <repo>/build/downloads), SSTATE_DIR (default
# <repo>/build/sstate-cache), PIPELINE_TARGET (required).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT=$(readlink -f "$HERE/../..")

DL_DIR="${DL_DIR:-$ROOT/build/downloads}"
SSTATE_DIR="${SSTATE_DIR:-$ROOT/build/sstate-cache}"
PIPELINE_TARGET="${PIPELINE_TARGET:-}"

if [ -z "$PIPELINE_TARGET" ]; then
    echo "pipeline-install: target not given -- set PIPELINE_TARGET" >&2
    exit 1
fi
TARGET="$PIPELINE_TARGET"
PIPELINE_LOCK="$HOME/.config/wisekiosk/pipeline.lock"
mkdir -p "$(dirname "$PIPELINE_LOCK")"
exec 9>"$PIPELINE_LOCK"
if ! flock -n 9; then
    echo "pipeline-install: pipeline lock held -- a run is in progress; refusing to touch the checkouts" >&2
    exit 1
fi
mkdir -p "$DL_DIR" "$SSTATE_DIR"
DL_DIR=$(readlink -f "$DL_DIR")
SSTATE_DIR=$(readlink -f "$SSTATE_DIR")
DRIVER="$HOME/wisekiosk-pipeline/driver"
TREE="$HOME/wisekiosk-pipeline/tree"
MAP=$(readlink -f "$ROOT/local/device-identity.md")
KEYS=$(readlink -f "$ROOT/local/keys")
ORIGIN_URL=$(git -C "$ROOT" remote get-url origin)

if [ -d "$DRIVER/.git" ]; then
    git -C "$DRIVER" fetch origin
    git -C "$DRIVER" checkout --detach origin/main
else
    git clone "$ORIGIN_URL" "$DRIVER"
    git -C "$DRIVER" checkout --detach origin/main
fi
if [ -d "$TREE/.git" ]; then
    git -C "$TREE" fetch origin
else
    git clone "$ORIGIN_URL" "$TREE"
fi
if [ -L "$DRIVER/local" ]; then
    echo "$DRIVER/local is a symlink -- refusing" >&2
    exit 1
fi
mkdir -p "$DRIVER/local"
ln -sf "$MAP" "$DRIVER/local/device-identity.md"
# local/keys: an empty bind-mount target -- docs/testing.md §"Running it".
mkdir -p "$TREE/local/keys"

# wisekiosk-hashserv.service (#172) is the one hash-equivalence server both
# trees use from here on, bound to this tree's own build/cache/hashserv.db.
# This tree's own bitbake writes that file directly whenever it runs with no
# BB_HASHSERVE override (today's "auto" default), so both the merge below and
# enabling the service -- its first start opens the same file -- refuse while
# a build is in progress here, the same way the pipeline lock above already
# refuses while a pipeline run is in progress.
mkdir -p "$ROOT/build"
DEV_BUILD_LOCK="$ROOT/build/bitbake.lock"
exec 8>"$DEV_BUILD_LOCK"
if ! flock -n 8; then
    echo "pipeline-install: this tree's own build is in progress ($DEV_BUILD_LOCK is locked) -- refusing to touch its hashserv.db or (re)start wisekiosk-hashserv.service" >&2
    exit 1
fi

# Before (re-)pointing the pipeline at the shared server, fold in whatever the
# pipeline's own now-retired copy already learned on its own: INSERT OR IGNORE
# on each table's real unique key (method+taskhash[+outhash]), never the
# surrogate id, so re-running this is a no-op once both sides agree.
DEV_HASHSERV_DB="$ROOT/build/cache/hashserv.db"
PIPELINE_HASHSERV_DB="$TREE/build/cache/hashserv.db"
if [ -f "$PIPELINE_HASHSERV_DB" ]; then
    if [ -f "$DEV_HASHSERV_DB" ]; then
        BEFORE=$("${py:-python3}" -c 'import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("select count(*) from unihashes_v3").fetchone()[0])' "$DEV_HASHSERV_DB")
        "${py:-python3}" -c '
import sqlite3, sys
dst = sqlite3.connect(sys.argv[1])
dst.execute("ATTACH DATABASE ? AS src", (sys.argv[2],))
dst.execute("""
    INSERT OR IGNORE INTO main.unihashes_v3 (method, taskhash, unihash, gc_mark)
    SELECT method, taskhash, unihash, gc_mark FROM src.unihashes_v3
""")
dst.execute("""
    INSERT OR IGNORE INTO main.outhashes_v2
        (method, taskhash, outhash, created, owner, PN, PV, PR, task, outhash_siginfo)
    SELECT method, taskhash, outhash, created, owner, PN, PV, PR, task, outhash_siginfo
    FROM src.outhashes_v2
""")
dst.commit()
dst.execute("DETACH DATABASE src")
dst.close()
' "$DEV_HASHSERV_DB" "$PIPELINE_HASHSERV_DB"
        AFTER=$("${py:-python3}" -c 'import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("select count(*) from unihashes_v3").fetchone()[0])' "$DEV_HASHSERV_DB")
        echo "pipeline-install: merged the pipeline's hashserv.db into this tree's -- unihashes_v3 rows $BEFORE -> $AFTER"
    else
        # This tree has never built; nothing to merge into, so the pipeline's
        # copy -- an sqlite3 online backup, which also captures live WAL
        # contents -- becomes the seed instead.
        mkdir -p "$(dirname "$DEV_HASHSERV_DB")"
        rm -f "$DEV_HASHSERV_DB.tmp"
        "${py:-python3}" -c 'import sqlite3, sys; src = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True); dst = sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()' \
            "$PIPELINE_HASHSERV_DB" "$DEV_HASHSERV_DB.tmp"
        mv -- "$DEV_HASHSERV_DB.tmp" "$DEV_HASHSERV_DB"
        echo "pipeline-install: seeded this tree's hashserv.db from the pipeline's copy (this tree had none)"
    fi
fi

CONF_DIR="$HOME/.config/wisekiosk"
mkdir -p "$CONF_DIR"
SSH_DIR="$CONF_DIR/pipeline-ssh"
# wisekiosk-hashserv.service's socket (#172) -- shared by this tree and the
# pipeline's, so a unihash either build learns is visible to the other.
HASHSERV_SOCK="$CONF_DIR/hashserv.sock"
# Read by systemd EnvironmentFile= and by pipeline-run's `.`.
{
    printf 'PATH="%s"\n' "$PATH"
    printf 'DL_DIR="%s"\n' "$DL_DIR"
    printf 'SSTATE_DIR="%s"\n' "$SSTATE_DIR"
    printf 'PIPELINE_DRIVER="%s"\n' "$DRIVER"
    printf 'PIPELINE_TREE="%s"\n' "$TREE"
    printf 'PIPELINE_SSH_DIR="%s"\n' "$SSH_DIR"
    printf 'PIPELINE_KEYS_DIR="%s"\n' "$KEYS"
    printf 'PIPELINE_HASHSERV="%s"\n' "$HASHSERV_SOCK"
    printf 'PIPELINE_DEV_ROOT="%s"\n' "$ROOT"
    printf 'PIPELINE_TARGET="%s"\n' "$TARGET"
    printf 'PIPELINE_LOCK="%s"\n' "$PIPELINE_LOCK"
} > "$CONF_DIR/pipeline.env"

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
if [ ! -f "$SSH_DIR/id_ed25519" ]; then
    ssh-keygen -t ed25519 -N "" -C "wisekiosk-pipeline" -f "$SSH_DIR/id_ed25519" -q
fi

# Host *: the testimage container dials TEST_TARGET_IP, a bare address.
{
    printf 'Host *\n'
    printf '    User root\n'
    printf '    IdentityFile ~/.ssh/id_ed25519\n'
    printf '    StrictHostKeyChecking accept-new\n'
    printf '    UserKnownHostsFile ~/.ssh/known_hosts\n'
} > "$SSH_DIR/config"

PUBKEY=$(cat "$SSH_DIR/id_ed25519.pub")
SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
$SSH "root@$TARGET" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && grep -qxF '$PUBKEY' ~/.ssh/authorized_keys || echo '$PUBKEY' >> ~/.ssh/authorized_keys"

TARGET_HOSTNAME=$($SSH -i "$SSH_DIR/id_ed25519" "root@$TARGET" hostname)
printf 'PIPELINE_TARGET_HOSTNAME="%s"\n' "$TARGET_HOSTNAME" >> "$CONF_DIR/pipeline.env"

if ! loginctl show-user "$(id -un)" -p Linger 2>/dev/null | grep -q '^Linger=yes$'; then
    loginctl enable-linger "$(id -un)"
fi

# Unlike the pipeline timer below, this one is wanted immediately: nothing
# shares the cache until it is up, and a clone that never runs this still
# builds as today (includes/base.yaml only forwards BB_HASHSERVE when
# PIPELINE_HASHSERV reaches tools/kas-run.sh's container, which happens only
# via this file or this tree's own .env).
systemctl --user enable --now "$DRIVER/tools/pipeline/wisekiosk-hashserv.service"

echo "the timer is NOT enabled -- run 'just pipeline-on' when ready"
echo "this tree's own builds share the pipeline's hash-equivalence cache only" \
     "once PIPELINE_HASHSERV=\"$HASHSERV_SOCK\" is in this tree's .env (see" \
     "docs/testing.md \"Running it\"); KIOSK_HOST follows the same convention"
