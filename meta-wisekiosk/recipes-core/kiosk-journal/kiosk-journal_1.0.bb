SUMMARY = "Persistent journal on /data, across A/B updates"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://99-kiosk-journal.conf file://persistent.conf file://kiosk-journal-flush.service file://kiosk-last-reset file://kiosk-journal-vacuum file://kiosk-journal-vacuum.service file://kiosk-journal-vacuum.timer"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR; the
# UNPACKDIR/sources layout is a later-release convention.
S = "${WORKDIR}"

inherit systemd

# Deliberately does NOT set VOLATILE_LOG_DIR. That variable is read by systemd's
# do_install, so changing it re-hashes systemd and then everything that depends
# on it, wpewebkit included (through udev) -- a multi-hour WebKit rebuild for a
# symlink. It also puts the journal on the rootfs slot, which an A/B update
# replaces, destroying the logs of the boot that failed.
SYSTEMD_SERVICE:${PN} = "kiosk-journal-flush.service kiosk-journal-vacuum.timer"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -d ${D}${nonarch_libdir}/tmpfiles.d
    install -m 0644 ${WORKDIR}/99-kiosk-journal.conf ${D}${nonarch_libdir}/tmpfiles.d/

    install -d ${D}${sysconfdir}/systemd/journald.conf.d
    install -m 0644 ${WORKDIR}/persistent.conf ${D}${sysconfdir}/systemd/journald.conf.d/

    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/kiosk-last-reset ${D}${bindir}/
    install -m 0755 ${WORKDIR}/kiosk-journal-vacuum ${D}${bindir}/

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/kiosk-journal-flush.service ${D}${systemd_system_unitdir}/
    install -m 0644 ${WORKDIR}/kiosk-journal-vacuum.service ${D}${systemd_system_unitdir}/
    install -m 0644 ${WORKDIR}/kiosk-journal-vacuum.timer ${D}${systemd_system_unitdir}/
}

FILES:${PN} += "${bindir}/kiosk-last-reset ${bindir}/kiosk-journal-vacuum ${nonarch_libdir}/tmpfiles.d ${sysconfdir}/systemd/journald.conf.d ${systemd_system_unitdir}/kiosk-journal-flush.service ${systemd_system_unitdir}/kiosk-journal-vacuum.service ${systemd_system_unitdir}/kiosk-journal-vacuum.timer"
