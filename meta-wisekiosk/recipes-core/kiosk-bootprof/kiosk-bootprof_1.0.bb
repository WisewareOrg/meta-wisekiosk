SUMMARY = "Boot profiler: per-window CPU, disk I/O and module load order"
DESCRIPTION = "Answers whether this single ARM11 core is busy, idle, or blocked in each \
boot window, and what udev loads in what order. Both questions decide whether a change is \
worth making: overlapping two phases only helps if one is blocked, and work queued ahead of \
brcmfmac delays the wlan0 gate that the whole boot waits on. \
\
Not shipped in the image -- it is instrumentation, and it costs ~240ms of a boot it is meant \
to measure. tests/diagnostics/test_boot_profile.py copies the binary and its unit onto the \
board for the one boot it measures, and the unit removes both again when it stops."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://kiosk-bootprof.c \
    file://measure-surf.sh \
"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

inherit deploy

# Built with the target toolchain rather than shipped as a prebuilt binary --
# the first version of this was cross-compiled by hand inside the kas container,
# which is neither reproducible nor tracked by any recipe.
do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} -O2 -Wall -Wextra -o kiosk-bootprof ${S}/kiosk-bootprof.c
}

# The binary never joins the image -- it is deployed beside it, for
# tests/diagnostics/test_boot_profile.py to copy onto the board for one boot.
do_deploy() {
    install -d ${DEPLOYDIR}
    install -m 0755 kiosk-bootprof ${DEPLOYDIR}/kiosk-bootprof
}
addtask deploy after do_compile before do_build

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${S}/measure-surf.sh ${D}${bindir}/measure-surf.sh
}

FILES:${PN} = " \
    ${bindir}/measure-surf.sh \
"

# xprop/xwininfo for measure-surf.sh; they are already in the image via
# packagegroup-core-x11, named here so the dependency is explicit rather than
# incidental.
RDEPENDS:${PN} = "xprop xwininfo"
