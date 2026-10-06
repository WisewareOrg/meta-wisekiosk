SUMMARY = "Firmware display capture: the composited output of display 0 as a PPM"
DESCRIPTION = "Snapshots what the firmware composed for display 0 through DispmanX \
over vchiq and writes binary PPM: the frame as sent to the panel rather than one \
DRM plane. Usage is in files/kiosk-fwgrab.c's header."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-fwgrab.c"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

DEPENDS = "userland"
RDEPENDS:${PN} = "userland"

inherit pkgconfig

# vc_dispmanx_snapshot is in libvchostif, which bcm_host.pc does not list.

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} -O2 -Wall -Wextra $(pkg-config --cflags bcm_host) \
        -o kiosk-fwgrab ${S}/kiosk-fwgrab.c $(pkg-config --libs bcm_host) -lvchostif
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 kiosk-fwgrab ${D}${bindir}/kiosk-fwgrab
}
