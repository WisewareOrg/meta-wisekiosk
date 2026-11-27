# Updates

## The shared /boot

The card's first partition, FAT and mounted at `/boot`, holds U-Boot, its environment
(`uboot.env`), `config.txt` and `cmdline.txt`, and both slots share it. RAUC writes only the
rootfs slots (`RAUC_BUNDLE_SLOTS = "rootfs"`), so nothing on `/boot` travels in an update: a
`config.txt` key, the kernel command line, a device-tree overlay and U-Boot's settings reach a board
only when its card is flashed. The kernel and its modules load from the rootfs slot, so they do
travel in an update and fall back with their slot.

A bad write to `/boot` breaks both slots at once, and the card has to be pulled. A change that can
live in the rootfs, as a unit or a sysctl, lives there, so an update carries it and a failed slot
falls back. Where a `/boot` file has to change on a running board by hand, the partition is backed
up first, each file is written atomically (temporary file, `fsync`, rename), and a restore puts back
the one file — never the whole partition, which overwrites `uboot.env` and with it both slots' boot
state.

## The first boot of a written slot

The first boot of a slot an update has just written does work no later boot repeats: the units
gated on `ConditionNeedsUpdate=` (`ldconfig`, the journal catalog update, the machine-id commit)
and OpenSSH's host-key generation. Until the host keys exist `sshd` accepts no session, so for tens
of seconds the board answers `ping` and refuses `ssh`; that is not a failed update. The same work
slows everything else on that boot, so a steady-state figure is read from the second boot.
