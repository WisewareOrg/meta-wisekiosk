# How an update reaches a slot

Every install — `just kiosk-ota`, [`tools/rauc-rotate.sh`](../../../tools/rauc-rotate.sh) and the
target suite's update tests — goes through [`tools/kiosk-install.sh`](../../../tools/kiosk-install.sh),
whose header says how. The board streams the bundle over HTTP from a pinned `nginx` container on the
host for the length of one install. The bundle is adaptive
(`RAUC_SLOT_rootfs[adaptive] = "block-hash-index"` in [`update-bundle.bbappend`](update-bundle.bbappend)),
so RAUC fetches and writes only the blocks neither slot already holds, and keeps each slot's index in
`/data/rauc`. The rootfs image is sized to its content
([`core-image-base.bbappend`](../images/core-image-base.bbappend)), and `resize=true` in RAUC's
`system.conf` grows the slot's filesystem to its partition after each write.

## Why

The distro sets `IMAGE_ROOTFS_SIZE` to the slot size, so an image built that way fills its slot, most
of it empty filesystem, and every install writes all of it.

RAUC's documentation names adaptive updates as an optimisation for HTTP streaming: the
`block-hash-index` method hashes both slots and fetches only blocks neither holds. Yocto's default
sizing is the content times `IMAGE_OVERHEAD_FACTOR` (1.3), and RAUC's `resize=true` is its documented
answer to an ext4 image smaller than its slot.

## Alternatives set aside

- **Copy the bundle with `scp`, then install from `/data`** — moved the whole bundle every time, and
  the tests needed a second install path beside it.
- **Adaptive bundles without streaming** — still copies the whole bundle, and on the bench a slot's
  first install was slower than a plain one (PR 335 image update behaviour, "Install times");
  RAUC documents adaptive mode as a streaming optimisation.
- **An `ssh -R` tunnel to a server on the host's loopback** — not RAUC's documented setup; the board
  reaches the host directly where the host publishes port 80 on the LAN.
- **A small Python server pinned in `uv.lock`** — a prebuilt, digest-pinned image needs no code of
  the layer's own.
- **casync bundles** — need a converted bundle and a separate chunk store; RAUC documents streaming
  with adaptive updates as their successor.
- **One install serving several tests in sequence** — would couple the update tests to each other.
- **A headroom figure of the layer's own** — Yocto's default factor plus `resize=true` is the
  documented combination.

## Consequences

- A slot's first adaptive install hashes the slot to build its index, so it is the slowest.
- The rootfs is formatted with 4 KiB blocks (`-b 4096`): `mke2fs` picks 1 KiB for an image this
  small, and `resize2fs` keeps the block size when it grows the filesystem.
- `rauc-conf` pulls in `e2fsprogs-resize2fs`, which `resize=true` runs on the board.
- `resize=true` is read from the running system's `system.conf`, so an install made from an image
  without it, as the one that first moves a board onto this layout is, leaves that slot's filesystem
  at its content size until the slot is next written.
- The host that installs needs Docker and a port 80 the board can reach at the address its ssh
  session comes from; [`docs/testing.md`](../../../docs/testing.md) §"Running it" states this for the
  bench.

## Reopen if

- An install is needed where the board cannot reach the installing host over HTTP.
- RAUC skips writing blocks already present in the target slot outside adaptive mode, which would
  remove the reason for streaming on a LAN.
