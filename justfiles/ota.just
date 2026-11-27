# OTA recipes. The casync recipes work on a casync bundle the image does not build.
#
# Variables set by the importing Justfile:
#   rauc-bundle-dir  - Directory for output bundles
#   rauc-cert        - Path to RAUC signing certificate
#   rauc-key         - Path to RAUC signing key
#   rauc-keyring     - Path to RAUC keyring

# Convert a RAUC bundle to casync format (casync; the image builds no casync bundle)
[group('ota')]
[script('bash')]
rauc-to-casync bundle:
    mkdir -p {{rauc-bundle-dir}}
    rauc convert \
        --cert={{rauc-cert}} \
        --key={{rauc-key}} \
        --keyring={{rauc-keyring}} \
        {{bundle}} \
        {{rauc-bundle-dir}}/$(basename {{bundle}} .raucb).caibx
    echo "Created casync bundle at {{rauc-bundle-dir}}/$(basename {{bundle}} .raucb).caibx"

# List new chunks between two casync stores (casync; the image builds no casync bundle)
[group('ota')]
[script('bash')]
casync-diff old-store new-store:
    NEW_CHUNKS=$(comm -23 \
        <(find {{new-store}} -name '*.cacnk' -printf '%f\n' 2>/dev/null | sort) \
        <(find {{old-store}} -name '*.cacnk' -printf '%f\n' 2>/dev/null | sort))
    echo "$NEW_CHUNKS"
    COUNT=$(echo "$NEW_CHUNKS" | grep -c . || true)
    SIZE=0
    for chunk in $NEW_CHUNKS; do
        prefix="${chunk:0:4}"
        if [ -f "{{new-store}}/$prefix/$chunk" ]; then
            SIZE=$((SIZE + $(stat -c%s "{{new-store}}/$prefix/$chunk")))
        fi
    done
    SIZE_MB=$((SIZE / 1024 / 1024))
    echo "" >&2
    echo "Delta: $COUNT chunks, ${SIZE_MB}MB" >&2

# Package new chunks and the bundle into a tarball (casync; the image builds no casync bundle)
[group('ota')]
[script('bash')]
casync-package-delta old-store new-store bundle output="update.tar.gz":
    STAGING=$(mktemp -d)
    trap "rm -rf $STAGING" EXIT

    NEW_CHUNKS=$(comm -23 \
        <(find {{new-store}} -name '*.cacnk' -printf '%f\n' 2>/dev/null | sort) \
        <(find {{old-store}} -name '*.cacnk' -printf '%f\n' 2>/dev/null | sort))

    mkdir -p "$STAGING/updates.castr"
    COUNT=0
    SIZE=0
    for chunk in $NEW_CHUNKS; do
        prefix="${chunk:0:4}"
        mkdir -p "$STAGING/updates.castr/$prefix"
        cp "{{new-store}}/$prefix/$chunk" "$STAGING/updates.castr/$prefix/"
        SIZE=$((SIZE + $(stat -c%s "{{new-store}}/$prefix/$chunk")))
        COUNT=$((COUNT + 1))
    done

    mkdir -p "$STAGING/rauc"
    cp "{{bundle}}" "$STAGING/rauc/"

    tar -czf "{{output}}" -C "$STAGING" updates.castr rauc

    SIZE_MB=$((SIZE / 1024 / 1024))
    TARBALL_SIZE=$(du -h "{{output}}" | cut -f1)
    echo "Packaged $COUNT chunks (${SIZE_MB}MB) + bundle manifest"
    echo "Created {{output}} ($TARBALL_SIZE)"
    echo "Deploy with: tar -xf {{output}} -C /data"

# Package all chunks and the bundle into a tarball (casync; the image builds no casync bundle)
[group('ota')]
[script('bash')]
casync-package store bundle output="update.tar.gz":
    STAGING=$(mktemp -d)
    trap "rm -rf $STAGING" EXIT

    mkdir -p "$STAGING/updates.castr"
    COUNT=0
    SIZE=0
    for chunk in $(find {{store}} -name '*.cacnk' 2>/dev/null); do
        prefix=$(basename $(dirname $chunk))
        mkdir -p "$STAGING/updates.castr/$prefix"
        cp "$chunk" "$STAGING/updates.castr/$prefix/"
        SIZE=$((SIZE + $(stat -c%s "$chunk")))
        COUNT=$((COUNT + 1))
    done

    mkdir -p "$STAGING/rauc"
    cp "{{bundle}}" "$STAGING/rauc/"

    tar -czf "{{output}}" -C "$STAGING" updates.castr rauc

    SIZE_MB=$((SIZE / 1024 / 1024))
    TARBALL_SIZE=$(du -h "{{output}}" | cut -f1)
    echo "Packaged $COUNT chunks (${SIZE_MB}MB) + bundle manifest"
    echo "Created {{output}} ($TARBALL_SIZE)"
    echo "Deploy with: tar -xf {{output}} -C /data"

# Show casync chunk store statistics (casync; the image builds no casync bundle)
[group('ota')]
[script('bash')]
casync-stats store:
    CHUNKS=$(find {{store}} -name '*.cacnk' 2>/dev/null | wc -l)
    SIZE=$(du -sh {{store}} 2>/dev/null | cut -f1)
    echo "Chunks: $CHUNKS"
    echo "Size: $SIZE"

# === Tier 1 delivery: the board streams the bundle from this host ===
# tools/kiosk-install.sh serves it and installs it; docs/updates.md §"Delivering an update".

kiosk-image-file := "build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/core-image-base-raspberrypi0-wifi.rootfs.ext4"
kiosk-bundle-file := "build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/update-bundle-raspberrypi0-wifi.raucb"

# `just build` makes only the kas `target:` images, not the bundle.
[group('ota')]
[doc("Build the RAUC update bundle")]
kiosk-bundle kconfig="kiosk-zero-w.yaml":
    tools/kas-run.sh shell {{kconfig}} -c "bitbake update-bundle"

[group('ota')]
[script('bash')]
[doc("Refuse a delivery that cannot work: slot size, stale bundle")]
kiosk-preflight image=kiosk-image-file bundle=kiosk-bundle-file host=kiosk-host:
    set -euo pipefail
    SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"

    test -f "{{image}}"  || { echo "no rootfs image at {{image}}"; exit 1; }
    test -f "{{bundle}}" || { echo "no bundle at {{bundle}}"; exit 1; }
    IMAGE_B=$(stat -Lc %s "{{image}}")

    # The gate checks the rootfs image, not the bundle.
    tools/reproducibility-gate.sh --image "{{image}}" || exit 1

    # Slot sizes from the device's block devices (sector count in 512-byte units).
    A_BYTES=$(( $($SSH {{host}} 'cat /sys/class/block/mmcblk0p2/size') * 512 ))
    B_BYTES=$(( $($SSH {{host}} 'cat /sys/class/block/mmcblk0p3/size') * 512 ))
    echo "rootfs image  : $IMAGE_B"
    echo "slot A / B    : $A_BYTES / $B_BYTES"
    for slot in "$A_BYTES" "$B_BYTES"; do
        if [ "$IMAGE_B" -gt "$slot" ]; then
            echo "REFUSING: the image does not fit a $slot-byte slot"
            exit 1
        fi
    done
    echo "preflight OK"

[group('ota')]
[doc("Stream a bundle to the board, install it and show slot state, without rebooting")]
kiosk-install host=kiosk-host bundle=kiosk-bundle-file:
    tools/kiosk-install.sh {{host}} {{bundle}}

# Reboot and wait for the kiosk to answer again.
[group('ota')]
[script('bash')]
kiosk-reboot host=kiosk-host timeout="300":
    SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
    BEFORE=$($SSH {{host}} 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null)
    $SSH -o ServerAliveInterval=2 -o ServerAliveCountMax=3 {{host}} 'systemctl reboot' >/dev/null 2>&1 || true
    T0=$(date +%s)
    while :; do
        NOW=$($SSH {{host}} 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null || true)
        [ -n "$NOW" ] && [ "$NOW" != "$BEFORE" ] && break
        [ $(( $(date +%s) - T0 )) -gt {{timeout}} ] && { echo "did not come back in {{timeout}}s"; exit 1; }
        sleep 5
    done
    echo "back after $(( $(date +%s) - T0 ))s, boot_id $NOW"
    $SSH {{host}} 'rauc status 2>&1 | grep -E "Booted|boot status"; systemctl is-active kiosk; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT'

# Build the bundle, preflight, and install it on the device
[group('ota')]
kiosk-ota host=kiosk-host kconfig="kiosk-zero-w.yaml": (kiosk-bundle kconfig) (kiosk-preflight kiosk-image-file kiosk-bundle-file host) (kiosk-install host kiosk-bundle-file)
    @echo "Delivered and installed. Verify, then: just kiosk-reboot {{host}}"

# Both slots mount the same /data, so a rollback leaves /data unchanged.
[group('ota')]
[script('bash')]
[doc("Roll back to the other slot")]
kiosk-rollback host=kiosk-host:
    SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
    $SSH {{host}} 'rauc status mark-bad booted; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT'
    echo "Marked booted slot bad. Now: just kiosk-reboot {{host}}"
