# bootfiles

`rpi-config_%.bbappend` appends three firmware HDMI settings to the `config.txt` that meta-raspberrypi
deploys: `hdmi_force_hotplug=1`, `hdmi_group=1` and `hdmi_mode=16` (CEA 1080p60). Forced hotplug brings
the output up when the display is off or slow to answer at boot.

## How it fits

- Firmware settings are inert under full KMS. The image builds firmware KMS (`VC4DTBO = "vc4-fkms-v3d"`
  in `kiosk-zero-w.yaml`), so they set the firmware's own mode.
- The kiosk's mode is set on top by `video=` in the kernel's `panel-mode.cfg`
  ([`recipes-kernel/linux`](../../recipes-kernel/linux/README.md)).
- `config.txt` lives on the shared `/boot`, so a change here reaches a board only when its card is
  flashed ([`docs/updates.md`](../../../docs/updates.md) §"The shared /boot").

Part of [the display](../../../docs/display.md).

## Knobs

- `hdmi_force_hotplug`, `hdmi_group`, `hdmi_mode`: the heredoc in `do_deploy:append`.
- `VC4DTBO`: `kiosk-zero-w.yaml`, not this module.
