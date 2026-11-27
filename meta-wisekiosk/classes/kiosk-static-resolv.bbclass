# Points /etc/resolv.conf at /data/config/resolv.conf and masks systemd-resolved (kiosk-hardware).
# The nameserver is site configuration written by provisioning, never baked into the image.
# A dangling symlink on an unprovisioned device means DNS fails; timesyncd is the only consumer.
#
# A rootfs postprocess, not a package: a package installing /etc/resolv.conf conflicts at
# do_rootfs with the package that already ships it as a symlink.
# /usr/lib/tmpfiles.d/systemd-resolve.conf carries `L! /etc/resolv.conf ...`; `L` creates only
# when the path does not exist and does not replace this symlink.

kiosk_set_static_resolv() {
    rm -f ${IMAGE_ROOTFS}${sysconfdir}/resolv.conf
    ln -s /data/config/resolv.conf ${IMAGE_ROOTFS}${sysconfdir}/resolv.conf
}

# Bare name, no trailing `;`: image.bbclass uses the raw value as vardeps and splits it on
# whitespace, so a glued `func;` names no function and its body reaches no task hash.
# tools/ci-guards.sh polices the trailing `;`.
ROOTFS_POSTPROCESS_COMMAND += "kiosk_set_static_resolv"
