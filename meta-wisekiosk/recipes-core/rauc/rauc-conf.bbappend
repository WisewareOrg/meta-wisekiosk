# Supplies this layer's files/${MACHINE}/system.conf; the autonomos bbappend prepends only its own directory.
FILESEXTRAPATHS:prepend := "${THISDIR}/files/${MACHINE}:"

# system.conf's resize=true grows each slot's filesystem with resize2fs after the write.
RDEPENDS:${PN}:append = " e2fsprogs-resize2fs"
