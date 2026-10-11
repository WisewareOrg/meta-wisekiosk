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

# PIPELINE_TARGET_ROLE: the role (prod or bench) whose local/device-identity.md
# address equals TARGET, through tools/device-role.py. Refuses outright on prod.
ROLE_LINE=$(python3 "$HERE/../device-role.py" "$TARGET") || exit 1
ROLE=${ROLE_LINE#role=}
ROLE=${ROLE%% *}
if [ "$ROLE" = "prod" ]; then
    echo "pipeline-install: PIPELINE_TARGET resolves to role=prod -- refusing to provision the pipeline against prod" >&2
    exit 1
fi

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

# hmac.key lives in local/keys (PIPELINE_KEYS_DIR), beside the fleet
# signing key. docs/testing.md § "Running it" has the why.
mkdir -p "$KEYS"
HMAC_KEY="$KEYS/hmac.key"
if [ ! -f "$HMAC_KEY" ]; then
    (umask 077 && head -c 32 /dev/urandom | base64 > "$HMAC_KEY")
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
    printf 'PIPELINE_TARGET_ROLE="%s"\n' "$ROLE"
    printf 'PIPELINE_LOCK="%s"\n' "$PIPELINE_LOCK"
    printf 'PIPELINE_REPLAY_PORT="%s"\n' "${PIPELINE_REPLAY_PORT:-18443}"
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

echo "the timer is NOT enabled -- run 'just pipeline-on' when ready"
