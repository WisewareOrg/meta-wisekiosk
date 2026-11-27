# Removes 99-com.rules (GPIO, i2c, spi, PWM and serial symlinks for add-on hardware); six of its
# rules fork a shell during udev coldplug. can.rules stays.
do_install:append() {
    rm -f ${D}${sysconfdir}/udev/rules.d/99-com.rules
}
