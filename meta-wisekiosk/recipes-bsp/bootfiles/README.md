# bootfiles

`rpi-config_%.bbappend` appends three firmware HDMI settings to the `config.txt` that meta-raspberrypi
deploys: `hdmi_force_hotplug=1`, `hdmi_group=1` and `hdmi_mode=16` (CEA 1080p60). Forced hotplug brings
the output up when the display is off or slow to answer at boot.

## How it fits

- Firmware settings are inert under full KMS. The image builds firmware KMS (`VC4DTBO = "vc4-fkms-v3d"`
  in `kiosk-zero-w.yaml`), so they set the firmware's own mode.
- The kiosk's mode is set on top by `video=` in the kernel's `panel-mode.cfg`
  ([`recipes-kernel/linux`](../../recipes-kernel/linux/README.md)).
- `config.txt` lives on the shared FAT `/boot` partition, which a RAUC update never writes; a change
  here reaches a board only by reflash.

Part of [the device](../../../docs/device.md).

## Knobs

- `hdmi_force_hotplug`, `hdmi_group`, `hdmi_mode`: the heredoc in `do_deploy:append`.
- `VC4DTBO`: `kiosk-zero-w.yaml`, not this module.
