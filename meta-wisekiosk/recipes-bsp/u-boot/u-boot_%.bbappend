# Sets CONFIG_BOOTDELAY=0 in the defconfig; delete-then-append is idempotent across rebuilds.
# No uboot.env is built: boot.cmd.in saves the compiled-in default on a card with no uboot.env,
# and a saved env keeps its own value.
do_configure:prepend:raspberrypi0-wifi() {
    sed -i '/^CONFIG_BOOTDELAY=/d' ${S}/configs/${UBOOT_MACHINE}
    echo 'CONFIG_BOOTDELAY=0' >> ${S}/configs/${UBOOT_MACHINE}
}
