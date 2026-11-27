SUMMARY = "Apply the site configuration on /data at boot"
DESCRIPTION = "A boot-time oneshot that sets the hostname from /data/config, keeps the machine-id on /data and seeds the app's config.json. The image carries no site configuration."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-provision file://kiosk-provision.service file://kiosk-seed-config"
S = "${WORKDIR}"

inherit systemd
SYSTEMD_SERVICE:${PN} = "kiosk-provision.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/kiosk-provision ${D}${bindir}/
    install -m 0755 ${WORKDIR}/kiosk-seed-config ${D}${bindir}/
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/kiosk-provision.service ${D}${systemd_system_unitdir}/
}

FILES:${PN} += "${bindir}/kiosk-provision ${bindir}/kiosk-seed-config ${systemd_system_unitdir}/kiosk-provision.service"
