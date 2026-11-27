#!/bin/sh
# RAUC slot hook. Runs on the running system with the freshly written slot mounted at
# $RAUC_SLOT_MOUNT_POINT, before that slot has booted.
#
# Copies this device's machine-id from /data/etc/machine-id into the new slot's /etc/machine-id;
# journald reads it at boot before /data is mounted. The first run seeds /data/etc/machine-id
# from the running system's.
#
# Every path exits 0: a non-zero exit from a hook aborts the install.

set -u

case "$1" in
    slot-post-install)
        [ -n "${RAUC_SLOT_MOUNT_POINT:-}" ] || {
            echo "kiosk-slot-hook: no RAUC_SLOT_MOUNT_POINT, skipping"
            exit 0
        }

        # Seed /data from the running system the first time.
        if [ ! -s /data/etc/machine-id ] && [ -s /etc/machine-id ]; then
            mkdir -p /data/etc
            cp /etc/machine-id /data/etc/machine-id
            echo "kiosk-slot-hook: seeded /data/etc/machine-id from the running system"
        fi

        if [ -s /data/etc/machine-id ]; then
            id=$(tr -d '[:space:]' < /data/etc/machine-id)
            # systemd accepts only 32 lowercase hex characters.
            if [ "${#id}" -eq 32 ] && [ -z "$(printf '%s' "$id" | tr -d '0-9a-f')" ]; then
                printf '%s\n' "$id" > "$RAUC_SLOT_MOUNT_POINT/etc/machine-id"
                chmod 0644 "$RAUC_SLOT_MOUNT_POINT/etc/machine-id"
                echo "kiosk-slot-hook: wrote machine-id into the new slot"
            else
                echo "kiosk-slot-hook: /data/etc/machine-id is malformed, leaving the slot's own"
            fi
        fi
        ;;
esac

exit 0
