#!/bin/bash
# Rotate the RAUC signing key on ONE device, over SSH, in two phases:
#
#   phase 1  install the TRANSITION bundle (new keyring, OLD-signed) to the
#            inactive slot and boot it.
#   phase 2  install the END-STATE bundle (new keyring, NEW-signed) to the other
#            slot.
#
# Each phase aborts unless the reboot lands on the OTHER slot with the new keyring. The host is
# passed explicitly to every kiosk-* recipe.
#
# Usage: rauc-rotate.sh <host> <new-keydir> [--one-slot]
#   --one-slot  stop after phase 1 (the fallback slot keeps trusting the old key)
set -euo pipefail

HOST=${1:?usage: rauc-rotate.sh <host> <new-keydir> [--one-slot]}
NEW_KEYDIR=${2:?need <new-keydir>}
ONE_SLOT=${3:-}

# `just rotate-run <host> --one-slot` binds the flag to `name`; refuse a flag as the key name.
case "$(basename "$NEW_KEYDIR")" in
    --*) echo "name the key explicitly before any flag: rotate-run <host> <name> --one-slot" >&2; exit 2;;
esac

REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"

SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
IMG="build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/core-image-base-raspberrypi0-wifi.rootfs.ext4"
T="build/rotation/transition.raucb"
N="build/rotation/new-signed.raucb"

fp()        { openssl x509 -in "$1" -noout -fingerprint -sha256 | sed 's/.*=//'; }
dev_fp()    { $SSH "$HOST" 'openssl x509 -in /etc/rauc/keyring.pem -noout -fingerprint -sha256' | sed 's/.*=//'; }
# Canonical booted-slot name (A/B), the same source the OTA recipes read.
dev_slot()  { $SSH "$HOST" 'rauc status --output-format=shell' | sed -n "s/^RAUC_SYSTEM_BOOTED_BOOTNAME='\(.*\)'/\1/p"; }
dev_certs() { $SSH "$HOST" 'grep -c "BEGIN CERTIFICATE" /etc/rauc/keyring.pem'; }
# Set the device clock from the host.
pin_clock() { $SSH "$HOST" "date -u -s '$(date -u '+%Y-%m-%d %H:%M:%S')'" >/dev/null; }

NEW_FP=$(fp "$NEW_KEYDIR/signing.cert.pem")
test -f "$T" || { echo "missing $T -- run: just rotate-build" >&2; exit 1; }
test -f "$N" || { echo "missing $N -- run: just rotate-build" >&2; exit 1; }
$SSH "$HOST" true 2>/dev/null || { echo "cannot reach $HOST over key auth -- run: just rotate-provision-ssh $HOST" >&2; exit 1; }

CUR_FP=$(dev_fp); SLOT0=$(dev_slot)
echo "device $HOST: booted slot ${SLOT0:-?}, trusts $CUR_FP"
echo "target new fp    : $NEW_FP"

if [ "$CUR_FP" = "$NEW_FP" ]; then
    echo "device already trusts the new key on the booted slot; skipping phase 1"
else
    echo "=== phase 1: transition bundle (new keyring, OLD-signed) -> inactive slot"
    pin_clock
    just kiosk-preflight "$IMG" "$T" "$HOST"
    just kiosk-install "$HOST" "$T"
    just kiosk-reboot "$HOST"
    SLOT1=$(dev_slot); FP1=$(dev_fp)
    if [ -z "$SLOT1" ] || [ "$SLOT1" = "$SLOT0" ]; then
        echo "!! transition slot did not boot: device is back on slot ${SLOT0:-?} (still trusts the old key)."
        echo "!! U-Boot rolled back on its own; the device is safe and bootable. Investigate the"
        echo "!! transition bundle -- do NOT force the failed slot."
        exit 1
    fi
    if [ "$FP1" != "$NEW_FP" ]; then
        echo "!! booted new slot $SLOT1 but its keyring is $FP1, not the new $NEW_FP."
        echo "!! recover with: just kiosk-rollback $HOST && just kiosk-reboot $HOST"
        exit 1
    fi
    [ "$(dev_certs)" = "1" ] || echo "note: device keyring holds more than one certificate"
    echo "phase 1 OK: slot ${SLOT0:-?} -> $SLOT1, device now trusts the new key ($FP1)"
fi

if [ "$ONE_SLOT" = "--one-slot" ]; then
    echo "--one-slot: stopping. The fallback slot still trusts the OLD key."
    echo "Re-run without --one-slot to bring the second slot onto the new key."
    exit 0
fi

echo "=== phase 2: end-state bundle (new keyring, NEW-signed) -> the other slot"
PRESLOT=$(dev_slot)
pin_clock
just kiosk-preflight "$IMG" "$N" "$HOST"
just kiosk-install "$HOST" "$N"
just kiosk-reboot "$HOST"
SLOT2=$(dev_slot); FP2=$(dev_fp)
if [ -z "$SLOT2" ] || [ "$SLOT2" = "$PRESLOT" ]; then
    echo "!! end-state slot did not boot: device rolled back to slot ${PRESLOT:-?} (trusts the new key)."
    echo "!! the device is safe, but the SECOND slot was never confirmed on the new key -- do NOT"
    echo "!! retire the old key yet. Investigate the end-state bundle and re-run rotate-run."
    exit 1
fi
if [ "$FP2" != "$NEW_FP" ]; then
    echo "!! phase 2 anomaly: booted $SLOT2 trusts $FP2 (want $NEW_FP)" >&2
    exit 1
fi
echo "rotation complete on $HOST: booted slot $SLOT2, both slots trust the new key ($FP2)"
echo "the old key is now retired on this device."
