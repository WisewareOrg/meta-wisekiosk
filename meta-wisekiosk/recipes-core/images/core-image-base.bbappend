# Sized to its content, not to the slot: see README.md §"Updating a running device".
# The distro sets IMAGE_ROOTFS_SIZE to the slot size; IMAGE_ROOTFS_MAXSIZE still
# holds the image to it.
IMAGE_ROOTFS_SIZE = "65536"
IMAGE_OVERHEAD_FACTOR = "1.3"

# mke2fs picks 1 KiB blocks for an image this small, and resize2fs keeps the
# block size, so a slot grown to its partition would carry 1 KiB blocks.
EXTRA_IMAGECMD:ext4:append = " -b 4096"
