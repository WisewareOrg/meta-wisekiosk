# The display

## Firmware KMS

The panel is driven through firmware KMS: `VC4DTBO = "vc4-fkms-v3d"` in
[`kiosk-zero-w.yaml`](../kiosk-zero-w.yaml) puts `dtoverlay=vc4-fkms-v3d` in `config.txt`, and mesa
provides EGL on top of it. Full KMS (`vc4-kms-v3d`) gives this panel a black picture on a live
signal, at every mode and compositing setting tried, so it is not an option on this display. The
value is set outright rather than taken as a default, because meta-raspberrypi spells `VC4DTBO` as a
weak `?=` that several of its machine configurations override.

Like every `config.txt` line, the overlay reaches a board only when its card is flashed:
[`updates.md`](updates.md) §"The shared /boot".
