# linux

`linux-raspberrypi_%.bbappend` adds a patch set and kernel config fragments to the Raspberry Pi kernel.
`FILESEXTRAPATHS:prepend` points at `files/`, and each item is a `SRC_URI` entry.

Patches (upstream format, not edited here):
- `brcmfmac-52e8726d6782.patch`: mainline commit 52e8726d6782 (v6.14), which makes the brcmfmac SDIO
  scatter-gather code fail the transfer on running out of list entries instead of dereferencing NULL.
- `0001-pstore-ram-default-ftrace-zone.patch`: `ramoops_parse_dt` defaults the pstore ftrace zone to
  64 KiB when `CONFIG_PSTORE_FTRACE` is enabled and the device tree gives no `ftrace-size`.

Config fragments:
- `lockup-detect.cfg`: soft-lockup detector, panicking on a lockup.
- `pstore-ftrace.cfg`: `CONFIG_PSTORE_FTRACE=y`.
- `panel-mode.cfg`: `CONFIG_CMDLINE_EXTEND=y` and `video=HDMI-A-1:1280x720@60` on the command line.
- `board.cfg`: switches off subsystems this board has no device or user for (media, Bluetooth, CAN,
  MTD, USB serial and storage, most filesystems, NFS and CIFS, mac80211 and non-Broadcom WLAN vendors,
  most traffic-control schedulers and classifiers, ram disks) and presets no loop devices.

## How it fits

- The recorders in `lockup-detect.cfg` and `pstore-ftrace.cfg` write to pstore, which survives a reset;
  `tools/kiosk-install.sh` lowers `kernel.watchdog_thresh` and arms the ftrace zone for the length of an
  install.
- The kernel version is held by `PREFERRED_VERSION_linux-raspberrypi` in `kiosk-zero-w.yaml`.
- `panel-mode.cfg` pairs with the firmware settings in [`recipes-bsp/bootfiles`](../../recipes-bsp/bootfiles/README.md).
- `board.cfg` leaves NETFILTER to meta-autonomos's `k3s-netfilter.cfg`, keeps SND and SND_SOC (DRM_VC4
  depends on them), and sets no symbol that something else selects, since such a line has no effect.
- Changing a fragment rebuilds the kernel and its modules.

Part of [the image](../../../docs/image.md).

## Knobs

- The panel mode: `video=` in `files/panel-mode.cfg`.
- Which subsystems are present: the `# CONFIG_X is not set` lines in `files/board.cfg`.
- Soft-lockup panic and pstore ftrace: the two small fragments.
