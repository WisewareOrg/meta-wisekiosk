SUMMARY = "Kiosk hardware trim: keep unused subsystems out of the boot, reboot on panic, and end memory thrash in an OOM kill"
DESCRIPTION = "Drop-in configuration only: the module blacklist, the watchdog, panic and MGLRU settings, and unit and udev-rule masks."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-blacklist.conf file://watchdog.conf file://60-kiosk-panic.conf file://60-kiosk-mglru.conf"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

do_install() {
    install -d ${D}${sysconfdir}/modprobe.d
    install -m 0644 ${WORKDIR}/kiosk-blacklist.conf ${D}${sysconfdir}/modprobe.d/

    install -d ${D}${sysconfdir}/systemd/system.conf.d
    install -m 0644 ${WORKDIR}/watchdog.conf ${D}${sysconfdir}/systemd/system.conf.d/

    install -d ${D}${sysconfdir}/sysctl.d
    install -m 0644 ${WORKDIR}/60-kiosk-panic.conf ${D}${sysconfdir}/sysctl.d/

    install -d ${D}${nonarch_libdir}/tmpfiles.d
    install -m 0644 ${WORKDIR}/60-kiosk-mglru.conf ${D}${nonarch_libdir}/tmpfiles.d/

    # Masks the SysV script's generated zram.service; zram-swap.service provides the swap.
    # The script stays in the package, which update-rc.d's postinst refers to.
    install -d ${D}${sysconfdir}/systemd/system
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/zram.service

    # Masked with a static /etc/resolv.conf (kiosk-static-resolv.bbclass).
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/systemd-resolved.service

    # logind owns seat and session management, which neither the browser nor the tty2 login uses.
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/systemd-logind.service
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/systemd-userdbd.service
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/systemd-userdbd.socket

    # With logind masked nothing starts autovt@tty2, so getty@tty2 is enabled at boot.
    install -d ${D}${sysconfdir}/systemd/system/getty.target.wants
    ln -sf ${systemd_system_unitdir}/getty@.service \
        ${D}${sysconfdir}/systemd/system/getty.target.wants/getty@tty2.service
    # tty1 belongs to the page; a login prompt there would take the keys typed at it.
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/getty@tty1.service

    # A /dev/null symlink in /etc/udev/rules.d shadows the /usr/lib rule file of the same name
    # (udev(7)); nothing under /usr/lib changes. Not masked: 71-seat, 73-seat-late, 70-uaccess,
    # 60-drm, 60-persistent-storage, the net rules, and 60-input-id, 60-evdev and the libinput
    # rules (60-input-id sets the ID_INPUT_* tags libinput selects devices by).
    install -d ${D}${sysconfdir}/udev/rules.d
    for r in ${KIOSK_UDEV_RULES_MASKED}; do
        ln -sf /dev/null ${D}${sysconfdir}/udev/rules.d/$r.rules
    done
}

KIOSK_UDEV_RULES_MASKED = "\
    78-sound-card 60-persistent-alsa 60-persistent-v4l 70-camera \
    60-persistent-input 70-mouse 70-touchpad 70-joystick \
    60-persistent-storage-tape 60-persistent-storage-mtd 75-probe_mtd \
    60-cdrom_id 60-infiniband 60-fido-id 90-iocost 60-sensor 64-btrfs 75-casync \
"

FILES:${PN} = " \
    ${sysconfdir}/modprobe.d/kiosk-blacklist.conf \
    ${sysconfdir}/systemd/system.conf.d/watchdog.conf \
    ${sysconfdir}/sysctl.d/60-kiosk-panic.conf \
    ${nonarch_libdir}/tmpfiles.d/60-kiosk-mglru.conf \
    ${sysconfdir}/systemd/system/zram.service \
    ${sysconfdir}/systemd/system/systemd-resolved.service \
    ${sysconfdir}/systemd/system/systemd-logind.service \
    ${sysconfdir}/systemd/system/systemd-userdbd.service \
    ${sysconfdir}/systemd/system/systemd-userdbd.socket \
    ${sysconfdir}/systemd/system/getty.target.wants/getty@tty2.service \
    ${sysconfdir}/systemd/system/getty@tty1.service \
    ${sysconfdir}/udev/rules.d \
"
