#!/usr/bin/env bash
# bench.toml's own [hooks] precondition: refuses a bench run when /data's
# config no longer matches the baseline tools/pipeline/accept-bench-config.sh
# recorded. A nonzero exit here is the runner's own failure, not the
# candidate's.
#
#   just bench-precondition
#
# Env: LG_BENCH_ADDRESS (local/device-identity.md, never written here).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

[ -n "${LG_BENCH_ADDRESS:-}" ] || { echo "bench-precondition.sh: LG_BENCH_ADDRESS not set" >&2; exit 2; }

ROLE_LINE=$(python3 "$HERE/device-role.py" "$LG_BENCH_ADDRESS") || {
    echo "bench-precondition.sh: could not resolve $LG_BENCH_ADDRESS to a role -- refusing" >&2
    exit 1
}
ROLE=${ROLE_LINE#role=}
ROLE=${ROLE%% *}
if [ "$ROLE" = "prod" ]; then
    echo "bench-precondition.sh: target resolves to role=prod -- refusing to run against prod" >&2
    exit 1
fi

MAC_FILE="$ROOT/local/bench-config.mac"
[ -f "$MAC_FILE" ] || {
    echo "bench-precondition.sh: no $MAC_FILE -- run tools/pipeline/accept-bench-config.sh first" >&2
    exit 2
}

KEY="$ROOT/local/keys/hmac.key"
[ -f "$KEY" ] || { echo "bench-precondition.sh: no $KEY" >&2; exit 2; }

# shellcheck disable=SC1090
. "$MAC_FILE"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
SSH_HOST="root@$LG_BENCH_ADDRESS"

# hex_read PATH -- see tools/pipeline/accept-bench-config.sh: one pre-assembled
# command string, not separate ssh arguments, so the remote shell's re-parse
# does not lose this format string's quoting.
hex_read() {
    # shellcheck disable=SC2029
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" "hexdump -ve '1/1 \"%02x\"' $1"
}

# Presence test matches tools/pipeline/accept-bench-config.sh's own exactly
# (a cat that succeeds or fails), not a separate test -f, so the two sides
# can never disagree about what "absent" means.
if ssh "${SSH_OPTS[@]}" "$SSH_HOST" cat /data/config/kiosk.conf > /dev/null 2>&1; then
    now_kiosk_conf_mac=$(hex_read /data/config/kiosk.conf | python3 "$HERE/pipeline/config-mac.py" "$KEY")
else
    now_kiosk_conf_mac=absent
fi
now_config_mac=$(hex_read /data/config/config.json | python3 "$HERE/pipeline/config-mac.py" "$KEY")

fail=0
if [ "$now_kiosk_conf_mac" != "${kiosk_conf_mac:-}" ]; then
    echo "bench-precondition.sh: kiosk.conf changed since the config was accepted" \
         "(${kiosk_conf_mac:-unset} -> $now_kiosk_conf_mac)" >&2
    fail=1
fi
if [ "$now_config_mac" != "${config_mac:-}" ]; then
    echo "bench-precondition.sh: config.json changed since the config was accepted" \
         "(${config_mac:-unset} -> $now_config_mac)" >&2
    fail=1
fi

[ "$fail" -eq 0 ] || exit 1
echo "bench-precondition.sh: /data's config matches the accepted baseline"
