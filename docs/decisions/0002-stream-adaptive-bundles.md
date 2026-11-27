# 0002 — Install updates by streaming adaptive RAUC bundles over HTTP from the installing host

**Status:** accepted
**Decided:** 2026-11-22 (PR #335 #252 Image update behaviour)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-27 — first written, from the bundle recipe's README (#422 Documentation map).

## Context

Every update, by hand, by the key rotation or by a test, installs a RAUC bundle into the slot the
board is not running. The distro sets `IMAGE_ROOTFS_SIZE` to the slot size, so an image built that
way fills its slot, most of it empty filesystem, and every install moved and wrote all of it. The
image-update tests install several bundles in one run, so the install path is both the operator's
update and a large share of the bench's time.

## Decision

**The board streams the bundle over HTTP from a short-lived server on the installing host, and the
bundle is adaptive.** `RAUC_SLOT_rootfs[adaptive] = "block-hash-index"` makes RAUC hash both slots
and fetch and write only the blocks neither already holds. The rootfs image is sized to its content
(Yocto's default sizing, the content times `IMAGE_OVERHEAD_FACTOR`), and `resize=true` in RAUC's
`system.conf` grows the slot's filesystem to its partition after each write. All three are RAUC's
and Yocto's documented answers: RAUC documents adaptive updates as an optimisation for HTTP
streaming, and `resize=true` as its answer to an ext4 image smaller than its slot.

## Alternatives considered

The transport was measured on the bench, one install path per run (PR #335 #252 Image update
behaviour, "Install times", which tabulates each test's install time under all three).

- **Copy the bundle to the board with `scp`, then install from `/data`.** Moves the whole bundle
  every time, and the tests needed a second install path beside it.
- **Adaptive bundles without streaming.** Still copies the whole bundle first, and a slot's first
  install was slower than a plain one; the adaptive saving is realised only when RAUC fetches by
  range, which is what streaming does.
- **casync bundles.** Need a converted bundle and a separate chunk store; RAUC documents streaming
  with adaptive updates as their successor. `RAUC_CASYNC_BUNDLE:pn-update-bundle = "0"` keeps the
  image from building one.

## Consequences

- A slot's first adaptive install hashes the slot to build its index, so it is the slowest; the
  indexes live in `/data/rauc`.
- The rootfs is formatted with 4 KiB blocks, because `mke2fs` picks 1 KiB for an image this small and
  `resize2fs` keeps the block size when it grows the filesystem; `rauc-conf` pulls in
  `e2fsprogs-resize2fs` for the board.
- `resize=true` is read from the running system's `system.conf`, so an install made from an image
  without it leaves that slot at its content size until the slot is next written.
- The installing host needs Docker and a port the board can reach at the address the host's ssh
  session comes from; NAT or an ssh jump between them breaks the install. The server holds the
  bundle in memory for one install, so the host needs the bundle's size free in memory.
- One install per board at a time from one host: a second install's set-up would clear the first's
  crash records, so `tools/kiosk-install.sh` refuses it and names the holder.

**Premise that would reopen this:** an install needed where the board cannot reach the installing
host over HTTP; or RAUC skipping blocks already present in the target slot outside adaptive mode,
which removes the reason to stream on a LAN.
