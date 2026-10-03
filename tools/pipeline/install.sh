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

# This tree's own bitbake writes build/cache/hashserv.db directly whenever it
# runs with BB_HASHSERVE unset (bitbake.lock is the same fcntl.flock bitbake
# itself takes on that TOPDIR). The merge and the service enable below both
# touch that file, so this gate sits beside the pipeline-lock gate above,
# before anything else is touched. Opened read-only -- never for writing --
# so a live holder's lock file (bitbake records its server pid in it) is
# never truncated; if it does not exist, this tree has never built here, so
# nothing can be mid-build and there is nothing to open.
DEV_BUILD_LOCK="$ROOT/build/bitbake.lock"
if [ -f "$DEV_BUILD_LOCK" ]; then
    exec 8<"$DEV_BUILD_LOCK"
    if ! flock -n 8; then
        echo "pipeline-install: this tree's own build is in progress ($DEV_BUILD_LOCK is locked) -- refusing to touch its hashserv.db or wisekiosk-hashserv.service" >&2
        exit 1
    fi
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

# wisekiosk-hashserv.service (#172 shared hashserv) is the one
# hash-equivalence server both trees use, bound to this tree's own
# build/cache/hashserv.db. Fold in whatever the pipeline's own copy already
# learned on its own before pointing it at the shared server: INSERT OR
# IGNORE on each table's real unique key (method+taskhash[+outhash]), never
# the surrogate id, so re-running this is a no-op once both sides agree. On a
# conflicting unihash for the same (method, taskhash), the dev tree's row
# wins (INSERT OR IGNORE never overwrites): a dev row exists only because
# this tree reported that task, so its sstate object is already in the
# shared SSTATE_DIR, which the pipeline's alternative chain for the same key
# is not guaranteed to be.
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
# wisekiosk-hashserv.service's socket (#172 shared hashserv) -- shared by
# this tree and the pipeline's, so a unihash either build learns is visible
# to the other. Its own directory, holding nothing else: kas-run.sh bind-
# mounts this directory whole into every build container, so anything else
# kept here would be readable and writable from inside one too.
HASHSERV_DIR="$CONF_DIR/hashserv"
mkdir -p "$HASHSERV_DIR"
HASHSERV_SOCK="$HASHSERV_DIR/hashserv.sock"
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

# There is no opt-in: this tree's own builds share the cache from the next
# `just build` on, the same as the pipeline's. Appended only if absent, so a
# line the operator edited (or a KIOSK_HOST already there) is left alone, and
# running this twice does not duplicate it.
ENV_FILE="$ROOT/.env"
if ! grep -q '^PIPELINE_HASHSERV=' "$ENV_FILE" 2>/dev/null; then
    printf 'PIPELINE_HASHSERV="%s"\n' "$HASHSERV_SOCK" >> "$ENV_FILE"
fi

# Unlike wisekiosk-pipeline.timer, which stays off until `just pipeline-on`,
# this service is wanted immediately: nothing shares the cache until it is up.
systemctl --user enable --now "$DRIVER/tools/pipeline/wisekiosk-hashserv.service"

# Fail closed rather than report success over a dead socket: a missing unit
# file (this PR not yet on origin/main), an absent sources/poky, or a down
# device would otherwise all look identical to a working install.
for _ in $(seq 1 100); do
    [ -S "$HASHSERV_SOCK" ] && break
    sleep 0.1
done
if [ ! -S "$HASHSERV_SOCK" ]; then
    echo "pipeline-install: wisekiosk-hashserv.service did not open its socket within 10s -- check 'systemctl --user status wisekiosk-hashserv.service'" >&2
    exit 1
fi

echo "the timer is NOT enabled -- run 'just pipeline-on' when ready"
