SUMMARY = "Scanout capture: the active CRTC's framebuffer as a PPM"
DESCRIPTION = "Reads the primary-plane framebuffer through DRM GETFB2 and a dma-buf \
mapping, de-tiles VC4 T-format, and writes binary PPM, optionally cropped: a capture \
that reads the scanout directly rather than through a display server. Usage and \
supported formats are in files/kiosk-drmgrab.c's header."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-drmgrab.c"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

DEPENDS = "libdrm"

inherit pkgconfig

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} -O2 -Wall -Wextra $(pkg-config --cflags libdrm) \
        -o kiosk-drmgrab ${S}/kiosk-drmgrab.c $(pkg-config --libs libdrm)
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 kiosk-drmgrab ${D}${bindir}/kiosk-drmgrab
}
