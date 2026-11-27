# u-boot

`u-boot_%.bbappend` sets `CONFIG_BOOTDELAY=0` in the machine's defconfig, which removes U-Boot's pause
before it boots the kernel. `do_configure:prepend` deletes any existing `CONFIG_BOOTDELAY=` line and
appends the new one, so rebuilds in the same `${S}` stay idempotent.

## How it fits

- The defconfig does not set the option, so U-Boot's Kconfig default of 2 seconds applies otherwise.
- No `uboot.env` is built or deployed. `boot.cmd.in` runs `saveenv` at first boot when `uboot.env` is
  absent from the FAT partition, which saves the compiled-in default. A card that already holds a saved
  env keeps its saved `bootdelay`; the change reaches a board only by reflash.
- The env block is shared with `BOOT_ORDER` and the RAUC slot counters, so it is baked into the build,
  not edited on a running board with `fw_setenv`.

Part of [the device](../../../docs/device.md).

## Knobs

- `CONFIG_BOOTDELAY`: the `echo` line in `do_configure:prepend:raspberrypi0-wifi`; changing it changes
  the pause (seconds) on freshly flashed cards.
