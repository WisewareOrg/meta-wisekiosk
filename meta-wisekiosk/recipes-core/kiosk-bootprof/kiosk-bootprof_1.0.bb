SUMMARY = "Boot profiler: per-window CPU, disk I/O and module load order"
DESCRIPTION = "A boot-time CPU and disk-I/O sampler and its analyzer, deployed beside the image and never installed in it."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-bootprof.c"
# scarthgap unpacks file:// SRC_URI straight into WORKDIR.
S = "${WORKDIR}"

inherit deploy

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} -O2 -Wall -Wextra -o kiosk-bootprof ${S}/kiosk-bootprof.c
}

# Deployed beside the image, never installed into it.
do_deploy() {
    install -d ${DEPLOYDIR}
    install -m 0755 kiosk-bootprof ${DEPLOYDIR}/kiosk-bootprof
}
addtask deploy after do_compile before do_build
