SUMMARY = "Withhold RAUC good-marking when a boot comes up with no usable LAN"
DESCRIPTION = "Covers the one failure class the A/B slots do not: a boot that completes \
normally and comes up unreachable. The watchdog stays quiet because nothing is wedged, and \
rauc-mark-good resets the boot counter regardless, so U-Boot never falls back and recovery \
needs a person with a USB keyboard. \
\
Ordered Before=boot-complete.target, which rauc-mark-good.service Requires. A non-zero exit \
leaves that target unreached, mark-good does not run, the boot counter is not reset, and \
three such boots drop the slot from BOOT_ORDER. When it withholds, restarts or suppresses \
itself is stated in the script's header."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-netcheck file://kiosk-netcheck.service"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "kiosk-netcheck.service"
SYSTEMD_AUTO_ENABLE = "enable"

# ip and ping are busybox applets here (/sbin/ip and /usr/bin/ping both symlink
# to it). fw_printenv is in libubootenv-bin, not libubootenv: the recipe inherits
# lib_package, which splits the binaries out of the library package.
RDEPENDS:${PN} = "busybox libubootenv-bin rauc"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/kiosk-netcheck ${D}${bindir}/

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/kiosk-netcheck.service ${D}${systemd_system_unitdir}/
}

FILES:${PN} += "${bindir}/kiosk-netcheck ${systemd_system_unitdir}/kiosk-netcheck.service"
