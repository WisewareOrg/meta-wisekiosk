SUMMARY = "Write the buffer the panel is scanning out to stdout"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-drmgrab.c"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

DEPENDS = "libdrm"

inherit pkgconfig

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} -Wall -Wextra $(pkg-config --cflags libdrm) \
        -o kiosk-drmgrab kiosk-drmgrab.c $(pkg-config --libs libdrm)
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 kiosk-drmgrab ${D}${bindir}/kiosk-drmgrab
}
