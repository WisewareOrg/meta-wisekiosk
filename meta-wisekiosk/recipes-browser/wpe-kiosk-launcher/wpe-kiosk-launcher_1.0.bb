SUMMARY = "Kiosk launcher on WebKit's WPE Platform DRM backend"
DESCRIPTION = "Loads one URL fullscreen through the WPE Platform API's DRM \
display, linked from libWPEWebKit-2.0. Usage, environment and exit codes are \
in files/wpe-kiosk-launcher.c's header."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://wpe-kiosk-launcher.c"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

DEPENDS = "wpewebkit libdrm"

inherit pkgconfig

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} -O2 -Wall -Wextra $(pkg-config --cflags wpe-webkit-2.0 libdrm) \
        -o wpe-kiosk-launcher ${S}/wpe-kiosk-launcher.c $(pkg-config --libs wpe-webkit-2.0 libdrm)
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 wpe-kiosk-launcher ${D}${bindir}/wpe-kiosk-launcher
}
