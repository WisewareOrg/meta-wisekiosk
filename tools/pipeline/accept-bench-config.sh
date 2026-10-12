#!/usr/bin/env bash
# Records bench's current /data config as bench-precondition's accepted
# baseline. Run only with the pipeline timer off, so the config this
# records is the one a job will actually see, not a seed a run left
# behind.
#
#   tools/pipeline/accept-bench-config.sh
#
# Env: LG_BENCH_ADDRESS (local/device-identity.md, never written here).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

[ -n "${LG_BENCH_ADDRESS:-}" ] || { echo "accept-bench-config.sh: LG_BENCH_ADDRESS not set" >&2; exit 2; }

if [ "$(systemctl --user is-enabled wisekiosk-pipeline.timer 2>/dev/null || true)" = "enabled" ] \
        || systemctl --user is-active --quiet wisekiosk-pipeline.service; then
    echo "accept-bench-config.sh: the pipeline timer is on -- 'just pipeline-off' first" >&2
    exit 1
fi

ROLE_LINE=$(python3 "$HERE/../device-role.py" "$LG_BENCH_ADDRESS") \
    || { echo "accept-bench-config.sh: could not resolve the target's role" >&2; exit 1; }
ROLE=${ROLE_LINE#role=}
ROLE=${ROLE%% *}
if [ "$ROLE" = "prod" ]; then
    echo "accept-bench-config.sh: target resolves to role=prod -- refusing to record prod's config" >&2
    exit 1
fi

KEY="$ROOT/local/keys/hmac.key"
if [ ! -f "$KEY" ]; then
    mkdir -p "$(dirname "$KEY")"
    (umask 077 && head -c 32 /dev/urandom | base64 > "$KEY")
    echo "accept-bench-config.sh: generated $KEY"
fi

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
SSH_HOST="root@$LG_BENCH_ADDRESS"

# hex_read PATH -- PATH's bytes on SSH_HOST as a hexdump -ve '1/1 "%02x"'
# dump: busybox has no base64 applet and no long-option od, and hex is
# the byte-safe transport the keyed hash needs. One pre-assembled
# string, not separate ssh arguments: ssh joins separate command words
# with spaces and the remote shell re-parses the result, which loses
# this format string's quoting.
hex_read() {
    # shellcheck disable=SC2029
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" "hexdump -ve '1/1 \"%02x\"' $1"
}

KIOSK_CONF=""
if KIOSK_CONF=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" cat /data/config/kiosk.conf 2>/dev/null); then
    # The cat above is for the key listing only; hex_read gets the bytes.
    KIOSK_CONF_HEX=$(hex_read /data/config/kiosk.conf)
    KIOSK_CONF_MAC=$(printf '%s' "$KIOSK_CONF_HEX" | python3 "$HERE/config-mac.py" "$KEY")
    echo "kiosk.conf keys (values never shown):"
    printf '%s\n' "$KIOSK_CONF" | grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' | sed 's/=$//' | sed 's/^/  /'
else
    KIOSK_CONF_MAC=absent
    echo "kiosk.conf: absent on bench"
fi

CONFIG_JSON_HEX=$(hex_read /data/config/config.json)
CONFIG_MAC=$(printf '%s' "$CONFIG_JSON_HEX" | python3 "$HERE/config-mac.py" "$KEY")

echo "kiosk_conf_mac=$KIOSK_CONF_MAC"
echo "config_mac=$CONFIG_MAC"

MAC_FILE="$ROOT/local/bench-config.mac"
mkdir -p "$(dirname "$MAC_FILE")"
printf 'kiosk_conf_mac=%s\nconfig_mac=%s\n' "$KIOSK_CONF_MAC" "$CONFIG_MAC" > "$MAC_FILE"
echo "recorded: $MAC_FILE"
