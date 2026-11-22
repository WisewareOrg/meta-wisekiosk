# meta-autonomos-raspberrypi's rauc-conf.bbappend prepends only its own
# files/${MACHINE} directory; raspberrypi0-wifi exists only in this layer.
FILESEXTRAPATHS:prepend := "${THISDIR}/files/${MACHINE}:"

# system.conf's resize=true grows each slot's filesystem with resize2fs after the write.
RDEPENDS:${PN}:append = " e2fsprogs-resize2fs"
