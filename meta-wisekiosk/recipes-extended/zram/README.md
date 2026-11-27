# zram

`zram_%.bbappend` adds `zram-default` to the upstream `zram` recipe and installs it as
`/etc/default/zram`: `ZRAM_SIZE_PERCENT=50` and `ZRAM_ALGORITHM=lzo-rle`, the size and the
compression algorithm of the zram swap device.

## How it fits

- The zram device size is its uncompressed capacity, so 50 % of RAM bounds what a full device can
  consume.
- `lzo-rle` is built into this kernel (`CONFIG_ZRAM_DEF_COMP`); `lz4` is a module, and asking for an
  algorithm behind an unloaded module leaves no swap while the unit looks healthy.
- The upstream recipe also ships a SysV `/etc/init.d/zram`. `kiosk-hardware` masks the generated
  `zram.service` (the script stays in the package, so the `update-rc.d` postinst still finds it);
  the systemd swap unit is the one that runs.
- `kiosk-zero-w.yaml` adds `zram` through `IMAGE_INSTALL`.

Part of [the device](../../../docs/device.md).

## Knobs

- `ZRAM_SIZE_PERCENT` and `ZRAM_ALGORITHM` in `zram/zram-default`.
