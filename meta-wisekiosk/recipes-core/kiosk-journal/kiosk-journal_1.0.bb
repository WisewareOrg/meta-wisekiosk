SUMMARY = "Persistent journal on /data, across A/B updates"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://99-kiosk-journal.conf file://persistent.conf file://kiosk-journal-flush.service"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

inherit systemd

# VOLATILE_LOG_DIR is left unset: systemd's do_install reads it.
SYSTEMD_SERVICE:${PN} = "kiosk-journal-flush.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -d ${D}${nonarch_libdir}/tmpfiles.d
    install -m 0644 ${WORKDIR}/99-kiosk-journal.conf ${D}${nonarch_libdir}/tmpfiles.d/

    install -d ${D}${sysconfdir}/systemd/journald.conf.d
    install -m 0644 ${WORKDIR}/persistent.conf ${D}${sysconfdir}/systemd/journald.conf.d/

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/kiosk-journal-flush.service ${D}${systemd_system_unitdir}/
}

FILES:${PN} += "${nonarch_libdir}/tmpfiles.d ${sysconfdir}/systemd/journald.conf.d ${systemd_system_unitdir}/kiosk-journal-flush.service"
