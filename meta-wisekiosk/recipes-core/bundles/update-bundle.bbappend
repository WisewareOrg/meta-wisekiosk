# Carries the device's machine-id into each freshly written slot (files/kiosk-slot-hook.sh).
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://kiosk-slot-hook.sh"

# CLOSED: insane.bbclass fails do_populate_lic for a recipe that fetches files without
# LIC_FILES_CHKSUM, and returns early only for CLOSED.
LICENSE = "CLOSED"

RAUC_BUNDLE_HOOKS[file] = "kiosk-slot-hook.sh"
RAUC_SLOT_rootfs[hooks] = "post-install"
# Adaptive bundle: RAUC fetches only blocks neither slot holds.
RAUC_SLOT_rootfs[adaptive] = "block-hash-index"
