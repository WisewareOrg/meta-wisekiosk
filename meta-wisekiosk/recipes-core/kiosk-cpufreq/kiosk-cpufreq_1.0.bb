SUMMARY = "Cap CPU frequency below the Pi Zero W's unstable top OPP"
DESCRIPTION = "A oneshot unit that caps scaling_max_freq at 900 MHz, below the board's top operating point."
LICENSE = "CLOSED"

SRC_URI = "file://kiosk-cpufreq-cap.service"

inherit systemd
SYSTEMD_SERVICE:${PN} = "kiosk-cpufreq-cap.service"
SYSTEMD_AUTO_ENABLE = "enable"

S = "${WORKDIR}"

do_install() {
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/kiosk-cpufreq-cap.service ${D}${systemd_system_unitdir}/
}

FILES:${PN} = "${systemd_system_unitdir}/kiosk-cpufreq-cap.service"
