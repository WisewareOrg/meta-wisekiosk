#!/usr/bin/env bash
# Provision the pipeline's checkouts, ssh key, env file and units.
# Env: PIPELINE_DRIVER_REF (default main), DL_DIR (default
# <repo>/build/downloads), SSTATE_DIR (default <repo>/build/sstate-cache),
# PIPELINE_TARGET (required).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT=$(readlink -f "$HERE/../..")

PIPELINE_DRIVER_REF="${PIPELINE_DRIVER_REF:-main}"
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
    git -C "$DRIVER" checkout -B "$PIPELINE_DRIVER_REF" "origin/$PIPELINE_DRIVER_REF"
else
    git clone --branch "$PIPELINE_DRIVER_REF" "$ORIGIN_URL" "$DRIVER"
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

# sqlite3 online backup: copies the live WAL contents too.
DEV_HASHSERV_DB="$ROOT/build/cache/hashserv.db"
PIPELINE_HASHSERV_DB="$TREE/build/cache/hashserv.db"
if [ -f "$DEV_HASHSERV_DB" ] && [ ! -f "$PIPELINE_HASHSERV_DB" ]; then
    mkdir -p "$TREE/build/cache"
    rm -f "$PIPELINE_HASHSERV_DB.tmp"
    "${py:-python3}" -c 'import sqlite3, sys; src = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True); dst = sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()' \
        "$DEV_HASHSERV_DB" "$PIPELINE_HASHSERV_DB.tmp"
    mv -- "$PIPELINE_HASHSERV_DB.tmp" "$PIPELINE_HASHSERV_DB"
fi

CONF_DIR="$HOME/.config/wisekiosk"
mkdir -p "$CONF_DIR"
SSH_DIR="$CONF_DIR/pipeline-ssh"
# Read by systemd EnvironmentFile= and by pipeline-run's `.`.
{
    printf 'PATH="%s"\n' "$PATH"
    printf 'DL_DIR="%s"\n' "$DL_DIR"
    printf 'SSTATE_DIR="%s"\n' "$SSTATE_DIR"
    printf 'PIPELINE_DRIVER="%s"\n' "$DRIVER"
    printf 'PIPELINE_TREE="%s"\n' "$TREE"
    printf 'PIPELINE_SSH_DIR="%s"\n' "$SSH_DIR"
    printf 'PIPELINE_KEYS_DIR="%s"\n' "$KEYS"
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

mkdir -p "$HOME/.config/systemd/user"
ln -sf "$DRIVER/tools/pipeline/wisekiosk-pipeline.service" "$HOME/.config/systemd/user/wisekiosk-pipeline.service"
ln -sf "$DRIVER/tools/pipeline/wisekiosk-pipeline.timer" "$HOME/.config/systemd/user/wisekiosk-pipeline.timer"
systemctl --user daemon-reload

if ! loginctl show-user "$(id -un)" -p Linger 2>/dev/null | grep -q '^Linger=yes$'; then
    loginctl enable-linger "$(id -un)"
fi

echo "the timer is NOT enabled -- run 'just pipeline-on' when ready"
