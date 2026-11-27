# files/wpa_supplicant.service shadows upstream's copy: the prepended path is searched ahead of the
# recipe's own, so its SRC_URI "file://wpa_supplicant.service" resolves here.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://robust.conf"

# The shadowed unit carries a bare ExecStart; systemd needs an absolute path.
do_install:append() {
    sed -i 's|^ExecStart=wpa_supplicant|ExecStart=${sbindir}/wpa_supplicant|' \
        ${D}${sysconfdir}/systemd/system/wpa_supplicant.service

    install -d ${D}${sysconfdir}/systemd/system/wpa_supplicant.service.d
    install -m 0644 ${WORKDIR}/robust.conf \
        ${D}${sysconfdir}/systemd/system/wpa_supplicant.service.d/robust.conf
}

FILES:${PN} += "${sysconfdir}/systemd/system/wpa_supplicant.service.d"
