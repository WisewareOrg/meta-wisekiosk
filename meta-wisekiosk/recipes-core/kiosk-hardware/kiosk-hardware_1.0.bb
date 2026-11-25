SUMMARY = "Kiosk hardware trim: keep unused subsystems out of the boot, reboot on panic, and end memory thrash in an OOM kill"
DESCRIPTION = "Drop-in configuration only -- no binaries, no services. Deliberately a \
separate recipe rather than a systemd_%.bbappend, which would rebuild WebKit: the \
chain is in recipes-core/kiosk-journal/kiosk-journal_1.0.bb."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-blacklist.conf file://watchdog.conf file://60-kiosk-panic.conf file://60-kiosk-mglru.conf"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

do_install() {
    # Camera, ISP, codec, audio and GPIO. Measured 2026-08-12: these load ahead
    # of brcmfmac in udev's queue, and wlan0 is the gate the whole boot waits on.
    install -d ${D}${sysconfdir}/modprobe.d
    install -m 0644 ${WORKDIR}/kiosk-blacklist.conf ${D}${sysconfdir}/modprobe.d/

    install -d ${D}${sysconfdir}/systemd/system.conf.d
    install -m 0644 ${WORKDIR}/watchdog.conf ${D}${sysconfdir}/systemd/system.conf.d/

    install -d ${D}${sysconfdir}/sysctl.d
    install -m 0644 ${WORKDIR}/60-kiosk-panic.conf ${D}${sysconfdir}/sysctl.d/

    install -d ${D}${nonarch_libdir}/tmpfiles.d
    install -m 0644 ${WORKDIR}/60-kiosk-mglru.conf ${D}${nonarch_libdir}/tmpfiles.d/

    # zram ships BOTH mechanisms for one job: zram_0.2.bb inherits update-rc.d
    # (/etc/init.d/zram, picked up by systemd-sysv-generator) and systemd
    # (zram-swap.service + dev-zram0.swap). The systemd path wins the race and
    # claims /dev/zram0; the SysV script then fails every boot with
    # "write error: Device or resource busy", burning 162ms to do it. Swap is
    # genuinely provided -- /dev/zram0, 208.8MB -- so masking costs no swap.
    # Masked rather than deleted from the package: removing the init script
    # would leave update-rc.d's postinst referring to a file that is not there.
    install -d ${D}${sysconfdir}/systemd/system
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/zram.service

    # systemd-resolved answers zero queries here -- resolvectl reports Total
    # Transactions 0 on a normal boot. It costs ~729ms starting at 19.96s, before
    # the gate, to write one file. Masking it with a static /etc/resolv.conf
    # (kiosk-static-resolv.bbclass) measured -1.03s at basic.target, n=3, ranges
    # not overlapping. DNS still resolves; timesyncd is the only consumer.
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/systemd-resolved.service

    # logind owns seat and session management, which neither the browser nor the
    # tty2 login uses.
    #
    # Measured n=3 at basic.target, on top of the resolved masking above:
    #   resolved masked only          21.30 / 21.15 / 21.07  mean 21.17
    #   + logind and userdbd masked   19.47 / 19.90 / 19.84  mean 19.74
    # -1.43s, ranges disjoint. Cumulative 22.20 -> 19.74.
    #
    # The display was verified as PIXELS, not as a process list: a framebuffer
    # capture rendered the clock to the second, the weather icons (which is the
    # complete-display endpoint), the park table and a current-cycle METAR.
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/systemd-logind.service
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/systemd-userdbd.service
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/systemd-userdbd.socket

    # With logind masked nothing starts autovt@tty2 on a console switch, so
    # getty@tty2 is enabled at every boot.
    install -d ${D}${sysconfdir}/systemd/system/getty.target.wants
    ln -sf ${systemd_system_unitdir}/getty@.service \
        ${D}${sysconfdir}/systemd/system/getty.target.wants/getty@tty2.service
    # tty1 belongs to the page; a login prompt there would take the keys typed at it.
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/getty@tty1.service

    # udev evaluates every rule file against all 345 device uevents. This board
    # has no sound card (/sys/class/sound empty) and no V4L (/sys/class/video4linux
    # absent) -- yet the image still ships rules for cameras, mice, touchpads,
    # joysticks, tape, MTD, CD-ROM, InfiniBand, FIDO and btrfs. Masking these cuts
    # the rule set udevd evaluates per uevent.
    #
    # A /dev/null symlink in /etc/udev/rules.d shadows the /usr/lib file of the
    # same name -- udev(7). Nothing under /usr/lib is modified, so this does not
    # re-hash systemd.
    #
    # NOT masked, deliberately: 71-seat, 73-seat-late and 70-uaccess (seat and
    # ACL handling), 60-drm (display), 60-persistent-storage and the net rules
    # (SD card and lifeline), and 60-input-id, 60-evdev and the libinput rules:
    # 60-input-id sets the ID_INPUT_* tags libinput picks an input device by, and
    # the other two set the device's evdev and libinput properties.
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
