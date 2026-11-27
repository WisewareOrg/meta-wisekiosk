# kiosk-cpufreq

`kiosk-cpufreq_1.0.bb` installs `kiosk-cpufreq-cap.service`, a oneshot enabled in `sysinit.target`.
At boot it writes `900000` to `/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq` and logs the
resulting cap to `/dev/kmsg`. The governor keeps scaling below the cap.

## How it fits

- Why the board needs the cap is [`docs/device.md`](../../../docs/device.md) §"CPU frequency".
- It is a unit in the rootfs, so an update carries it and a failed slot falls back
  ([`docs/updates.md`](../../../docs/updates.md) §"The shared /boot").
- `kiosk-zero-w.yaml` adds the package through `IMAGE_INSTALL`.

Part of [the device](../../../docs/device.md).

## Knobs

- The `900000` (kHz) in the first `ExecStart=` of `files/kiosk-cpufreq-cap.service` is the cap.
- `systemctl disable --now kiosk-cpufreq-cap` removes the cap on a running board until the next
  update.
