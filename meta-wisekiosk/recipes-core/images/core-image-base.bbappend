# Why: meta-wisekiosk/recipes-core/bundles/README.md. The distro's IMAGE_ROOTFS_MAXSIZE still applies.
IMAGE_ROOTFS_SIZE = "65536"
IMAGE_OVERHEAD_FACTOR = "1.3"
EXTRA_IMAGECMD:ext4:append = " -b 4096"
