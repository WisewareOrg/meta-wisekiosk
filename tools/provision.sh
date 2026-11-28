#!/usr/bin/env bash
# Write per-site configuration to a device's /data. The image carries none of it.
#
#   tools/provision.sh device root@<host>     -- a running, reachable device
#   tools/provision.sh card   /mnt/data       -- a mounted /data partition
#   tools/provision.sh stage  <outdir>        -- the output alone, no card or ssh
#
# Values come from secrets.yaml and are never echoed. Use `card` mode before first boot and
# `device` mode for a unit that is already reachable.
set -euo pipefail

MODE=${1:?usage: provision.sh device <ssh-target> | card <mounted-/data> | stage <outdir>}
DEST=${2:?usage: provision.sh device <ssh-target> | card <mounted-/data> | stage <outdir>}
SEC=${KIOSK_SECRETS:-$HOME/.config/wisekiosk/secrets.yaml}

# The kiosk-recover recipe's files/ copy is installed as /data/RECOVER.sh.
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RECOVER_SRC="$REPO/meta-wisekiosk/recipes-core/kiosk-recover/files/kiosk-recover"
[ -r "$RECOVER_SRC" ] || { echo "recovery script missing at $RECOVER_SRC"; exit 1; }

[ -r "$SEC" ] || {
    echo "no secrets at $SEC"
    echo "copy secrets.yaml.tmpl there and fill it in, or set KIOSK_SECRETS"
    exit 1
}

val() { sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\"\(.*\)\"[[:space:]]*$/\1/p" "$SEC" | head -n1; }
SSID=$(val WIFI_SSID);      PSK=$(val WIFI_PSK_HASH)
URL=$(val KIOSK_URL);       HOST=$(val KIOSK_HOSTNAME)
NS=$(val KIOSK_NAMESERVER); MID=$(val KIOSK_MACHINE_ID)

for pair in SSID:WIFI_SSID PSK:WIFI_PSK_HASH HOST:KIOSK_HOSTNAME NS:KIOSK_NAMESERVER; do
    n=${pair%%:*}; real=${pair#*:}
    [ -n "${!n}" ] || { echo "secrets.yaml is missing $real"; exit 1; }
done

# machine-id: 32 lowercase hex, generated per device when secrets.yaml has none.
if [ -z "$MID" ]; then
    MID=$(od -An -tx1 -N16 /dev/urandom | tr -d ' \n')
    echo "generated a machine-id (not stored in secrets.yaml -- add it to keep it stable)"
fi
if [ "${#MID}" -ne 32 ] || [ -n "$(printf '%s' "$MID" | tr -d '0-9a-f')" ]; then
    echo "KIOSK_MACHINE_ID must be 32 lowercase hex characters"; exit 1
fi

STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/config" "$STAGE/etc"
chmod 0755 "$STAGE/config" "$STAGE/etc"
umask 077
cat > "$STAGE/config/wpa_supplicant.conf" <<EOF
ctrl_interface=/var/run/wpa_supplicant
ctrl_interface_group=0
update_config=1

network={
    key_mgmt=WPA-PSK
    ssid="$SSID"
    psk=$PSK
}
EOF
umask 022
# Unset KIOSK_URL writes a comment-only kiosk.conf, so kiosk.service uses its own default.
if [ -n "$URL" ]; then
    printf 'KIOSK_URL=%s\n' "$URL" > "$STAGE/config/kiosk.conf"
else
    # a comment, not an empty file: kiosk-provision logs UNPROVISIONED for an empty one
    printf '# no KIOSK_URL: kiosk.service uses its own default\n' > "$STAGE/config/kiosk.conf"
fi
printf '%s\n' "$HOST" > "$STAGE/config/hostname"
: > "$STAGE/config/resolv.conf"
for ns in $NS; do printf 'nameserver %s\n' "$ns" >> "$STAGE/config/resolv.conf"; done
printf '%s\n' "$MID" > "$STAGE/etc/machine-id"
install -m 0755 "$RECOVER_SRC" "$STAGE/RECOVER.sh"

case "$MODE" in
  card)
    [ -d "$DEST" ] || { echo "$DEST is not a directory -- mount the /data partition first"; exit 1; }
    mkdir -p "$DEST/config" "$DEST/etc"
    cp "$STAGE/config/"* "$DEST/config/"
    cp "$STAGE/etc/machine-id" "$DEST/etc/machine-id"
    cp "$STAGE/RECOVER.sh" "$DEST/RECOVER.sh"
    chown -R 0:0 "$DEST/config" "$DEST/etc" 2>/dev/null || echo "note: run as root to own the files correctly"
    chown 0:0 "$DEST/RECOVER.sh" 2>/dev/null || true
    chmod 0600 "$DEST/config/wpa_supplicant.conf"
    chmod 0755 "$DEST/RECOVER.sh"

    #   mode        wpa_supplicant.conf must be 0600; fires when $DEST is the vfat boot partition,
    #               which accepts a chmod and ignores it
    #   ownership   files must be owned 0:0; the chown above only notes a failure
    bad=0
    say() { printf 'VERIFY FAIL  %s\n' "$*" >&2; bad=1; }

    mode=$(stat -c %a "$DEST/config/wpa_supplicant.conf")
    [ "$mode" = "600" ] || say "wpa_supplicant.conf is mode $mode, must be 600"

    for f in "$DEST/config/"* "$DEST/etc/machine-id"; do
        own=$(stat -c %u:%g "$f")
        [ "$own" = "0:0" ] || say "$f is owned by $own, must be 0:0 -- re-run as root"
    done

    # Checked apart from the loop above so a missing RECOVER.sh reports VERIFY FAIL instead of a stat error.
    if [ -f "$DEST/RECOVER.sh" ]; then
        own=$(stat -c %u:%g "$DEST/RECOVER.sh")
        [ "$own" = "0:0" ] || say "$DEST/RECOVER.sh is owned by $own, must be 0:0 -- re-run as root"
    else
        say "RECOVER.sh not delivered to $DEST -- recovery script missing"
    fi

    if [ "$bad" -ne 0 ]; then
        echo "NOT provisioned -- do not boot this card" >&2
        exit 1
    fi

    sync
    echo "provisioned $DEST"
    ;;
  stage)
    # Needs no card, ssh or root; skips the card branch's chown/mode enforcement.
    mkdir -p "$DEST/config" "$DEST/etc"
    cp "$STAGE/config/"* "$DEST/config/"
    cp "$STAGE/etc/machine-id" "$DEST/etc/machine-id"
    cp "$STAGE/RECOVER.sh" "$DEST/RECOVER.sh"
    echo "staged $DEST"
    ;;
  device)
    # --owner/--group stop tar preserving this host's uid/gid. The archive names STAGE's children,
    # not `.`, so /data keeps its own mode. rc is captured per remote step to name the failing one.
    rc=0
    tar -C "$STAGE" --owner=root --group=root --numeric-owner -cf - config etc RECOVER.sh | "$REPO/tools/kiosk-ssh.sh" "$DEST" \
        'mkdir -p /data/config /data/etc && tar -C /data -xf - && chown -R 0:0 /data/config /data/etc && chmod 0600 /data/config/wpa_supplicant.conf && sync' || rc=$?
    [ "$rc" -eq 0 ] || { echo "could not write /data on $DEST (tar|ssh rc=$rc) -- nothing was provisioned" >&2; exit 1; }

    rc=0
    "$REPO/tools/kiosk-ssh.sh" "$DEST" 'ls -l /data/config /data/etc/machine-id /data/RECOVER.sh' || rc=$?
    [ "$rc" -eq 0 ] || { echo "wrote /data on $DEST but could not read it back (ssh rc=$rc) -- check it by hand" >&2; exit 1; }
    echo "provisioned $DEST"
    ;;
  *) echo "unknown mode $MODE"; exit 1 ;;
esac
