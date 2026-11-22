# Sized to its content, with 4 KiB blocks: meta-wisekiosk/recipes-core/bundles/README.md.
# IMAGE_ROOTFS_MAXSIZE, which the distro sets to the slot size, still holds the image to it.
IMAGE_ROOTFS_SIZE = "65536"
IMAGE_OVERHEAD_FACTOR = "1.3"
EXTRA_IMAGECMD:ext4:append = " -b 4096"
