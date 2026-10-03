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

# >> matches bitbake's own bb.utils.lockfile() open: creates the file
# without truncating a live holder's.
mkdir -p "$ROOT/build"
DEV_BUILD_LOCK="$ROOT/build/bitbake.lock"
exec 8>>"$DEV_BUILD_LOCK"
if ! flock -n 8; then
    echo "pipeline-install: this tree's own build is in progress ($DEV_BUILD_LOCK is locked) -- refusing to touch its hashserv.db or wisekiosk-hashserv.service" >&2
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

CONF_DIR="$HOME/.config/wisekiosk"
mkdir -p "$CONF_DIR"
SSH_DIR="$CONF_DIR/pipeline-ssh"
# Its own directory, holding nothing else: kas-run.sh bind-mounts this whole
# into every build container.
HASHSERV_DIR="$CONF_DIR/hashserv"
mkdir -p "$HASHSERV_DIR"
HASHSERV_SOCK="$HASHSERV_DIR/hashserv.sock"
HASHSERV_DB="$HASHSERV_DIR/hashserv.db"

# Seed the shared db from this tree's own build/cache/hashserv.db, then fold
# in the pipeline's copy. docs/testing.md "Running it" has the why.
DEV_HASHSERV_DB="$ROOT/build/cache/hashserv.db"
PIPELINE_TREE_HASHSERV_DB="$TREE/build/cache/hashserv.db"
if [ ! -f "$HASHSERV_DB" ]; then
    if [ -f "$DEV_HASHSERV_DB" ]; then
        # An sqlite3 online backup, which also captures live WAL contents.
        rm -f "$HASHSERV_DB.tmp"
        "${py:-python3}" -c 'import sqlite3, sys; src = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True); dst = sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()' \
            "$DEV_HASHSERV_DB" "$HASHSERV_DB.tmp"
        mv -- "$HASHSERV_DB.tmp" "$HASHSERV_DB"
        echo "pipeline-install: seeded the shared hashserv.db from this tree's own copy"
    else
        "${py:-python3}" -c 'import sqlite3, sys; sqlite3.connect(sys.argv[1]).close()' "$HASHSERV_DB"
        echo "pipeline-install: created an empty shared hashserv.db (neither tree has built yet)"
    fi
fi
if [ -f "$PIPELINE_TREE_HASHSERV_DB" ]; then
    BEFORE=$("${py:-python3}" -c 'import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("select count(*) from unihashes_v3").fetchone()[0])' "$HASHSERV_DB")
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
' "$HASHSERV_DB" "$PIPELINE_TREE_HASHSERV_DB"
    AFTER=$("${py:-python3}" -c 'import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("select count(*) from unihashes_v3").fetchone()[0])' "$HASHSERV_DB")
    echo "pipeline-install: merged the pipeline's hashserv.db into the shared one -- unihashes_v3 rows $BEFORE -> $AFTER"
fi
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
    printf 'PIPELINE_HASHSERV_DB="%s"\n' "$HASHSERV_DB"
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

# Replace an existing PIPELINE_HASHSERV= line in place, else append (with a
# leading newline if the file has content and none of its own).
ENV_FILE="$ROOT/.env"
if grep -q '^PIPELINE_HASHSERV=' "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^PIPELINE_HASHSERV=.*|PIPELINE_HASHSERV=\"$HASHSERV_SOCK\"|" "$ENV_FILE"
else
    if [ -s "$ENV_FILE" ] && [ "$(tail -c1 "$ENV_FILE" | wc -l)" -eq 0 ]; then
        printf '\n' >> "$ENV_FILE"
    fi
    printf 'PIPELINE_HASHSERV="%s"\n' "$HASHSERV_SOCK" >> "$ENV_FILE"
fi

# Wanted immediately, unlike wisekiosk-pipeline.timer. docs/testing.md
# "Running it" has the why.
systemctl --user enable --now "$DRIVER/tools/pipeline/wisekiosk-hashserv.service"

# Checks both the socket's type and the unit's state. docs/testing.md
# "Running it" has the why.
hashserv_ready() {
    [ -S "$HASHSERV_SOCK" ] && systemctl --user is-active --quiet wisekiosk-hashserv.service
}
for _ in $(seq 1 100); do
    hashserv_ready && break
    sleep 0.1
done
if ! hashserv_ready; then
    echo "pipeline-install: wisekiosk-hashserv.service did not come up within 10s -- check 'systemctl --user status wisekiosk-hashserv.service'" >&2
    exit 1
fi

echo "the timer is NOT enabled -- run 'just pipeline-on' when ready"
