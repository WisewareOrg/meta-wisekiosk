SUMMARY = "Persist the timesyncd clock on /data, across A/B updates"
DESCRIPTION = "Binds systemd-timesyncd's saved clock onto /data, so a slot an update has written boots with a recent time."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-timesync-dir.service file://10-persist-clock.conf"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

inherit systemd

# The oneshot that stages the /data bind source.
SYSTEMD_SERVICE:${PN} = "kiosk-timesync-dir.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/kiosk-timesync-dir.service ${D}${systemd_system_unitdir}/

    install -d ${D}${systemd_system_unitdir}/systemd-timesyncd.service.d
    install -m 0644 ${WORKDIR}/10-persist-clock.conf ${D}${systemd_system_unitdir}/systemd-timesyncd.service.d/
}

FILES:${PN} += "\
    ${systemd_system_unitdir}/kiosk-timesync-dir.service \
    ${systemd_system_unitdir}/systemd-timesyncd.service.d/10-persist-clock.conf \
"
