SUMMARY = "Recovery script that reverses kiosk-hardware's boot trims; placed on /data by provisioning"
DESCRIPTION = "A script that reverses kiosk-hardware's boot trims and reboots. tools/provision.sh places it on /data; no image installs it."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://kiosk-recover"
S = "${WORKDIR}"

# Installs nothing: tools/provision.sh places the script on /data as RECOVER.sh.
do_install() {
    :
}
