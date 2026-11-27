# rauc

`rauc-conf.bbappend` supplies this machine's RAUC configuration, `files/raspberrypi0-wifi/system.conf`:
bootloader `uboot`, compatible string `autonomos-raspberrypi0-wifi`, the keyring at
`/etc/rauc/keyring.pem`, status and data under `/data/rauc`, and two ext4 rootfs slots, `A` on
`/dev/mmcblk0p2` and `B` on `/dev/mmcblk0p3`, each with `resize=true`. The bbappend also adds
`e2fsprogs-resize2fs` to `RDEPENDS`, which `resize=true` runs on the board.

## How it fits

- meta-autonomos-raspberrypi's own `rauc-conf.bbappend` prepends only its `files/${MACHINE}` directory;
  this one prepends the layer's, so `raspberrypi0-wifi` resolves here.
- `compatible` and the keyring decide which bundles the board accepts; see
  [`docs/updates.md`](../../../docs/updates.md) §"The one-way lock".
- `resize=true` is read from the running system's `system.conf`, so an install made from an image whose
  file lacks it leaves that slot's filesystem at its content size until the slot is next written.
- `/data/rauc` holds the status file and each slot's adaptive-update index.

Part of [the updates path](../../../docs/updates.md).

## Knobs

- Slot devices and `bootname`: the `[slot.rootfs.N]` sections.
- `compatible`, `[keyring] path`: the one-way lock of [`docs/updates.md`](../../../docs/updates.md) §"The one-way lock".
