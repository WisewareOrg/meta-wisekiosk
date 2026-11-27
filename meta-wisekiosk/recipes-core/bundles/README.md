# bundles

`update-bundle.bbappend` configures the RAUC bundle built from the image. It marks the rootfs slot
adaptive (`RAUC_SLOT_rootfs[adaptive] = "block-hash-index"`), so RAUC fetches and writes only the blocks
neither slot already holds and keeps each slot's index in `/data/rauc`. It also attaches
`files/kiosk-slot-hook.sh` as the bundle's hook file, run as the rootfs slot's `post-install` hook, and
sets `LICENSE = "CLOSED"`: `insane.bbclass` fails `do_populate_lic` for a recipe that fetches files
without `LIC_FILES_CHKSUM` unless it is `CLOSED`.

The hook runs on the running system with the freshly written slot mounted at `$RAUC_SLOT_MOUNT_POINT`.
It copies the device's machine-id from `/data/etc/machine-id` into the new slot's `/etc/machine-id`,
seeding `/data/etc/machine-id` from the running system's on the first run. A value that is not 32
lowercase hex characters is left out, and every path exits 0 because a non-zero exit aborts the install.

## How it fits

- journald reads `/etc/machine-id` early in boot, before `/data` is mounted, so the value has to be in
  the slot's rootfs; this hook is the point where the new slot is writable and the old system still knows
  the identity. A new identity per update would give each slot its own journal namespace, and
  `SystemMaxUse` is enforced per machine-id.
- Every install goes through [`tools/kiosk-install.sh`](../../../tools/kiosk-install.sh), which serves
  the bundle to the board over HTTP; why it is streamed and adaptive is
  [`docs/updates.md`](../../../docs/updates.md) §"Delivering an update".
- The rootfs is sized to its content by [`core-image-base.bbappend`](../images/README.md); `resize=true`
  in RAUC's [`system.conf`](../rauc/README.md) grows the slot's filesystem after each write.
- `RAUC_SLOT_rootfs` names the image and is set in `kiosk-zero-w.yaml`; the signing key is covered in
  [`docs/updates.md`](../../../docs/updates.md).

Part of [the updates path](../../../docs/updates.md).

## Knobs

- `RAUC_SLOT_rootfs[adaptive]`: `update-bundle.bbappend`; removing it makes a plain bundle that carries
  and writes the whole image.
- `RAUC_SLOT_rootfs[hooks]` and `RAUC_BUNDLE_HOOKS[file]`: which hook runs and where.
