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

for v in PIPELINE_TARGET PIPELINE_DRIVER; do
    [ -n "${!v:-}" ] || { echo "accept-bench-config.sh: $v not set" >&2; exit 2; }
done

if [ "$(systemctl --user is-enabled wisekiosk-pipeline.timer 2>/dev/null || true)" = "enabled" ] \
        || systemctl --user is-active --quiet wisekiosk-pipeline.service; then
    echo "accept-bench-config.sh: the pipeline timer is on -- 'just pipeline-off' first" >&2
    exit 1
fi

KEY="$ROOT/local/hmac.key"
[ -f "$KEY" ] || { echo "accept-bench-config.sh: no $KEY -- run 'just pipeline-install' first" >&2; exit 1; }

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
SSH_HOST="root@$PIPELINE_TARGET"

KIOSK_CONF=""
if KIOSK_CONF=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" cat /data/config/kiosk.conf 2>/dev/null); then
    KIOSK_CONF_MAC=$(printf '%s' "$KIOSK_CONF" | python3 "$HERE/config-mac.py" "$KEY")
    echo "kiosk.conf keys (values never shown):"
    printf '%s\n' "$KIOSK_CONF" | grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' | sed 's/=$//' | sed 's/^/  /'
else
    KIOSK_CONF_MAC=absent
    echo "kiosk.conf: absent on bench"
fi

CONFIG_JSON=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" cat /data/config/config.json)
CONFIG_MAC=$(printf '%s' "$CONFIG_JSON" | python3 "$HERE/config-mac.py" "$KEY")

echo "kiosk_conf_mac=$KIOSK_CONF_MAC"
echo "config_mac=$CONFIG_MAC"

MAC_FILE="$PIPELINE_DRIVER/local/pipeline/bench-config.mac"
mkdir -p "$(dirname "$MAC_FILE")"
printf 'kiosk_conf_mac=%s\nconfig_mac=%s\n' "$KIOSK_CONF_MAC" "$CONFIG_MAC" > "$MAC_FILE"
echo "recorded: $MAC_FILE"
