# classes

Two bbclasses, both enabled from `kiosk-zero-w.yaml`.

- `kiosk-static-resolv.bbclass` (`INHERIT`): a rootfs postprocess, `kiosk_set_static_resolv`, replaces
  `/etc/resolv.conf` with a symlink to `/data/config/resolv.conf` and so keeps systemd-resolved
  unneeded (kiosk-hardware masks it). The nameserver is site configuration that provisioning writes to
  `/data/config`; the image bakes none. On an unprovisioned device the symlink dangles and DNS fails;
  timesyncd is the only consumer.
- `kiosk-buildinfo-cachesafe.bbclass` (`IMAGE_CLASSES`): requires `KIOSK_BUILDINFO_REV` (from
  `conf/build-rev.inc`, written by `tools/write-build-rev.sh`), fails the parse when it is unset, and adds
  it to `do_image[vardeps]`. `image-buildinfo` reads git inside `do_image` but hashes nothing, so without
  the entry bitbake replays a stale `/etc/buildinfo`.

## How it fits

- `kiosk_set_static_resolv` is a postprocess because a package that installs `/etc/resolv.conf` conflicts
  at `do_rootfs` with the package that already ships it as a symlink. systemd's
  `tmpfiles.d/systemd-resolve.conf` carries `L! /etc/resolv.conf`; `L` creates only when the path does
  not exist, so it leaves this symlink alone.
- `ROOTFS_POSTPROCESS_COMMAND` takes the bare function name, never `name;`: `image.bbclass` splits the
  raw value on whitespace into vardeps, so a glued `;` names no function and the body reaches no task
  hash. `tools/ci-guards.sh` checks for the trailing `;`.
- `just build` runs `tools/write-build-rev.sh`, which supplies `KIOSK_BUILDINFO_REV`. How the commit
  reaches the image is in [`docs/image.md`](../../docs/image.md) §"What commit an image was built from".

Part of [the image](../../docs/image.md).

## Knobs

- `INHERIT += "kiosk-static-resolv"` and `IMAGE_CLASSES += "kiosk-buildinfo-cachesafe"`: `kiosk-zero-w.yaml`.
- The resolv.conf target: the `ln -s` line in the class.
