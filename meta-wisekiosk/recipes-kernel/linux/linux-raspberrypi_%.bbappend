FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# brcmfmac SDIO: mainline 52e8726d6782 (v6.14) adds an `if (!sgl)` check, so running off the end
# of the scatterlist returns -ENOMEM instead of dereferencing NULL.
SRC_URI += " file://brcmfmac-52e8726d6782.patch"

# Soft-lockup detector, panicking into pstore; tools/kiosk-install.sh lowers
# kernel.watchdog_thresh to 1 for the length of an install.
SRC_URI += " file://lockup-detect.cfg"

# pstore ftrace zone, sized by the patch when the device tree gives none;
# tools/kiosk-install.sh arms it for the length of an install.
SRC_URI += " file://pstore-ftrace.cfg"
SRC_URI += " file://0001-pstore-ram-default-ftrace-zone.patch"

# The HDMI mode, set with video= on the kernel command line; WPE shows its page at the mode it finds set.
SRC_URI += " file://panel-mode.cfg"

# Subsystems this board has no device or user for, and fewer devices at coldplug.
SRC_URI += " file://board.cfg"
