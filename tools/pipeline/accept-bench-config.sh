#!/usr/bin/env bash
# Records bench's current /data config as the pre-job precondition's
# accepted baseline. docs/testing.md "Running it" -- run only with the
# pipeline timer off, so the config this records is the one a job will
# actually see, not a seed a run left behind.
#
#   tools/pipeline/accept-bench-config.sh
#
# Env: PIPELINE_TARGET, PIPELINE_DRIVER (both already in pipeline.env).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

# Self-sources the installed env when called directly, not through a
# justfile recipe that already sourced it. Runtime-generated, not a
# tracked file -- nothing for shellcheck to resolve.
if [ -z "${PIPELINE_TARGET:-}" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$HOME/.config/wisekiosk/pipeline.env"
    set +a
fi

for v in PIPELINE_TARGET PIPELINE_DRIVER; do
    [ -n "${!v:-}" ] || { echo "accept-bench-config.sh: $v not set" >&2; exit 2; }
done

if [ "$(systemctl --user is-enabled wisekiosk-pipeline.timer 2>/dev/null || true)" = "enabled" ] \
        || systemctl --user is-active --quiet wisekiosk-pipeline.service; then
    echo "accept-bench-config.sh: the pipeline timer is on -- 'just pipeline-off' first" >&2
    exit 1
fi

KEY="$ROOT/local/keys/hmac.key"
[ -f "$KEY" ] || { echo "accept-bench-config.sh: no $KEY -- run 'just pipeline-install' first" >&2; exit 1; }

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
SSH_HOST="root@$PIPELINE_TARGET"

# hex_read PATH -- PATH's bytes on SSH_HOST as a hexdump -ve '1/1 "%02x"'
# dump: busybox has no base64 applet and no long-option od, and hex is
# the byte-safe transport the keyed hash needs. One pre-assembled
# string, not separate ssh arguments: ssh joins separate command words
# with spaces and the remote shell re-parses the result, which loses
# this format string's quoting. docs/testing.md § "Running it" has the
# why.
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

# The replay CA cert: pushed from this host's own local/keys/replay-ca --
# tools/replay/ca.sh's own output -- never read as a pre-existing bench
# file the way kiosk.conf/config.json are above, since this file is
# host-managed, not something a person hand-places on bench.
CA_CERT="$ROOT/local/keys/replay-ca/ca.crt"
if [ -f "$CA_CERT" ]; then
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" \
            'mkdir -p /data/config/replay-ca && cat > /data/config/replay-ca/ca.crt && chmod 644 /data/config/replay-ca/ca.crt' \
            < "$CA_CERT" \
        || { echo "accept-bench-config.sh: could not install the replay CA cert on bench" >&2; exit 1; }
    CA_CERT_HEX=$(hex_read /data/config/replay-ca/ca.crt)
    CA_CERT_MAC=$(printf '%s' "$CA_CERT_HEX" | python3 "$HERE/config-mac.py" "$KEY")
else
    CA_CERT_MAC=absent
    echo "replay CA: no $CA_CERT -- run 'tools/replay/ca.sh <dir> ca' first, or every job will refuse the /data precondition"
fi

echo "kiosk_conf_mac=$KIOSK_CONF_MAC"
echo "config_mac=$CONFIG_MAC"
echo "ca_cert_mac=$CA_CERT_MAC"

MAC_FILE="$PIPELINE_DRIVER/local/pipeline/bench-config.mac"
mkdir -p "$(dirname "$MAC_FILE")"
printf 'kiosk_conf_mac=%s\nconfig_mac=%s\nca_cert_mac=%s\n' "$KIOSK_CONF_MAC" "$CONFIG_MAC" "$CA_CERT_MAC" > "$MAC_FILE"
echo "recorded: $MAC_FILE"
