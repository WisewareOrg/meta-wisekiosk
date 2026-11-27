# udev

`udev-rules-rpi.bbappend` extends the `udev-rules-rpi` recipe: its `do_install:append` deletes
`99-com.rules` from `/etc/udev/rules.d` in the package. That file is GPIO, i2c, spi, PWM and serial
symlink plumbing for add-on hardware this kiosk does not have; six of its rules fork a shell during
udev coldplug on the single core. `can.rules` stays, as it installs no `PROGRAM` rules.

## How it fits

- Rule files from other packages are masked by `kiosk-hardware` with `/dev/null` symlinks; this
  module removes a file at its source because the package is ours to append to.
- `kiosk-recover` removes only the `/dev/null` symlinks, so a removed file stays removed.

Part of [the device](../../../docs/device.md).
