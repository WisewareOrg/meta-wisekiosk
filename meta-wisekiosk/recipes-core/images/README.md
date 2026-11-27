# images

`core-image-base.bbappend` sizes the rootfs image to its content instead of to the slot:
`IMAGE_ROOTFS_SIZE = "65536"` (KiB, the floor), `IMAGE_OVERHEAD_FACTOR = "1.3"` and 4 KiB ext4 blocks
(`-b 4096`; `mke2fs` picks 1 KiB for an image this small).

## How it fits

- The image is the rootfs of the RAUC bundle ([`recipes-core/bundles`](../bundles/README.md)), so its
  size is what an install writes. RAUC's `resize=true` in
  [`system.conf`](../rauc/README.md) grows the slot's filesystem to the partition after each write;
  `resize2fs` keeps the 4 KiB block size.
- The distro's `IMAGE_ROOTFS_MAXSIZE` still applies.
- Which packages the image carries is `IMAGE_INSTALL` in `kiosk-zero-w.yaml`.

Part of [the image](../../../docs/image.md).

## Knobs

- `IMAGE_ROOTFS_SIZE`, `IMAGE_OVERHEAD_FACTOR`: headroom over the content.
- `EXTRA_IMAGECMD:ext4`: filesystem creation flags.
