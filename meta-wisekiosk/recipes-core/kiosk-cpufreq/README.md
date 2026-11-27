# kiosk-cpufreq

`kiosk-cpufreq_1.0.bb` installs `kiosk-cpufreq-cap.service`, a oneshot enabled in `sysinit.target`.
At boot it writes `900000` to `/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq` and logs the
resulting cap to `/dev/kmsg`. The governor keeps scaling below the cap.

## How it fits

- At the top operating point (1000 MHz) under sustained SDIO and network load this board corrupts
  memory: oopses in the network receive path, captured through pstore. Every lower operating point
  holds. The cap costs about a tenth of peak CPU.
- It is a unit in the image because the alternative knob, `over_voltage`, lives in `config.txt` on
  the shared FAT `/boot`, which an update never writes.
- `kiosk-zero-w.yaml` adds the package through `IMAGE_INSTALL`.

Part of [the device](../../../docs/device.md).

## Knobs

- The `900000` (kHz) in the first `ExecStart=` of `files/kiosk-cpufreq-cap.service` is the cap.
- `systemctl disable --now kiosk-cpufreq-cap` removes the cap on a running board until the next
  update.
