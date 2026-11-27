# Adds KIOSK_BUILDINFO_REV, the host-resolved sha, to do_image[vardeps] so /etc/buildinfo
# re-stamps when HEAD moves; image-buildinfo reads git in do_image but hashes nothing.

include conf/build-rev.inc

# Appended after image.bbclass's own vardeps append, which has no separator; the leading space
# keeps the tokens apart.
python () {
    if not d.getVar('KIOSK_BUILDINFO_REV'):
        bb.fatal("KIOSK_BUILDINFO_REV is unset: run tools/write-build-rev.sh "
                 "before bitbake, or build through `just build` / `just "
                 "kiosk-bundle`, which do it for you. Without it the image "
                 "cannot be kept in step with the commit it was built from.")
    d.appendVarFlag('do_image', 'vardeps', ' KIOSK_BUILDINFO_REV')
}
