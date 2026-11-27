SUMMARY = "Withhold RAUC good-marking when a boot comes up with no usable LAN"
DESCRIPTION = "A oneshot ordered before boot-complete.target that withholds marking the booted slot good until the LAN answers."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-netcheck file://kiosk-netcheck.service"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "kiosk-netcheck.service"
SYSTEMD_AUTO_ENABLE = "enable"

# ip and ping are busybox applets; fw_printenv is in libubootenv-bin, which lib_package splits
# out of libubootenv.
RDEPENDS:${PN} = "busybox libubootenv-bin rauc"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/kiosk-netcheck ${D}${bindir}/

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/kiosk-netcheck.service ${D}${systemd_system_unitdir}/
}

FILES:${PN} += "${bindir}/kiosk-netcheck ${systemd_system_unitdir}/kiosk-netcheck.service"
