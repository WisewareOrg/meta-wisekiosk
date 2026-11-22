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

The distro sets `IMAGE_ROOTFS_SIZE` to the slot size, so the image an install wrote was the whole
2 GB slot, most of it empty filesystem, and the bundle was copied to the board before the write began.

RAUC's documentation names adaptive updates as an optimisation for HTTP streaming: the
`block-hash-index` method hashes both slots and fetches only blocks neither holds. Yocto's default
sizing is the content times `IMAGE_OVERHEAD_FACTOR` (1.3), and RAUC's `resize=true` is its documented
answer to an ext4 image smaller than its slot.

## Measured

`install_s` of the update tests on the bench board, each run named by its record and the commit it
built. The figure is the whole of `tools/kiosk-install.sh`, which includes arming the install capture.

| Install | Plain, copied first (`20261121T202406Z`, `65a20f6`) | Adaptive, copied first (`20261121T211210Z`, `519d731`) | Streamed adaptive, content-sized (`20261121T232604Z`, `555626c`) |
|---|---|---|---|
| A slot's first adaptive install (TST006) | 184.6 s | 402.5 s | 445.6 s |
| A later install (TST023, TST024) | 159.7 s (TST023; TST024's install did not complete) | 141.5 s, 133.2 s | 103.2 s, 101.3 s |

A run's first two installs each index a slot, so the board stage of the six update tests took about
as long with streaming as without: 51 min in `20261121T211210Z` and 52 min in `20261121T232604Z`. The
saving is in every install after a slot holds its index.

## Alternatives set aside

- **Copy the bundle with `scp`, then install from `/data`** — moved the whole bundle every time, and
  the tests needed a second install path beside it.
- **Adaptive bundles without streaming** — a slot's first install took 402.5 s against a plain
  install's 184.6 s, and the bundle was still copied whole; RAUC documents adaptive mode as a
  streaming optimisation.
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
- The host that installs needs Docker and a port 80 the board can reach at the address its ssh
  session comes from; [`docs/testing.md`](../../../docs/testing.md) §"Running it" states this for the
  bench.

## Reopen if

- An install is needed where the board cannot reach the installing host over HTTP.
- RAUC skips writing blocks already present in the target slot outside adaptive mode, which would
  remove the reason for streaming on a LAN.
