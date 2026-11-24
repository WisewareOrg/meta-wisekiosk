SUMMARY = "Kiosk session: one page on WPE WebKit, straight to DRM, under systemd"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk.service file://kiosk-browser.c"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR; the
# UNPACKDIR/sources layout is a later-release convention.
S = "${WORKDIR}"

DEPENDS = "wpewebkit"
# WPE crashes at start without a keymap, and opens libEGL at run time.
RDEPENDS:${PN} = "xkeyboard-config libegl-mesa"

inherit pkgconfig systemd

SYSTEMD_SERVICE:${PN} = "kiosk.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_compile() {
    ${CC} ${CFLAGS} $(pkg-config --cflags wpe-webkit-2.0) -o kiosk-browser kiosk-browser.c \
        ${LDFLAGS} $(pkg-config --libs wpe-webkit-2.0)
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 kiosk-browser ${D}${bindir}/kiosk-browser

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 kiosk.service ${D}${systemd_system_unitdir}/kiosk.service
}
