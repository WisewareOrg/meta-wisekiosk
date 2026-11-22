# How an update reaches a slot

Every install — `just kiosk-ota`, [`tools/rauc-rotate.sh`](../../../tools/rauc-rotate.sh) and the
target suite's update tests — goes through [`tools/kiosk-install.sh`](../../../tools/kiosk-install.sh).
The board streams the bundle over HTTP from a pinned `nginx` container on the host for the length of
one install. The bundle is adaptive (`RAUC_SLOT_rootfs[adaptive] = "block-hash-index"` in
[`update-bundle.bbappend`](update-bundle.bbappend)), so RAUC fetches and writes only the blocks the
slots do not already hold. The rootfs image is sized to its content
([`core-image-base.bbappend`](../images/core-image-base.bbappend)), and `resize=true` in RAUC's
`system.conf` grows the slot's filesystem to its partition after each write.

## Why

On a Raspberry Pi Zero W an install was the slow part of every bench run: a 2 GB image written whole
into its slot, after the ~128 MB bundle was first copied to the board. The image filled the slot
because the distro sets `IMAGE_ROOTFS_SIZE` to the slot size, so it carried about 1.8 GB of empty
filesystem through every install.

RAUC's own documentation names adaptive updates as an optimisation for HTTP streaming, and the
`block-hash-index` method reads both slots and fetches only blocks neither holds. Yocto's default
sizing is the content times `IMAGE_OVERHEAD_FACTOR` (1.3), and RAUC's `resize=true` is its documented
answer to an ext4 image smaller than its slot.

## Alternatives set aside

- **Copy the bundle with `scp`, then install from `/data`** — moved the whole bundle every time and
  needed a second install path for the tests.
- **Adaptive bundles without streaming** — measured slower than a plain install on a slot's first
  adaptive install (the slot is indexed on the spot) and saved little after it: RAUC documents
  adaptive mode as a streaming optimisation.
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

- A slot's first adaptive install reads and hashes the slot to build its index, so it is the slowest;
  later installs reuse the index kept in `/data/rauc`.
- The rootfs is formatted with 4 KiB blocks (`-b 4096`): `mke2fs` would pick 1 KiB for an image this
  small, and `resize2fs` keeps the block size when it grows the filesystem.
- `rauc-conf` pulls in `e2fsprogs-resize2fs`, which `resize=true` runs on the board.
- The host that installs needs Docker and a port 80 the board can reach at the address its ssh
  session comes from; [`docs/testing.md`](../../../docs/testing.md) §"Running it" states this for the
  bench.

## Reopen if

- An install path is needed where the board cannot reach the installing host over HTTP.
- RAUC skips writing blocks already present in the target slot outside adaptive mode, which would
  remove the reason for streaming on a LAN.
