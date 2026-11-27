# kiosk-hardware

Drop-in configuration only: no binaries and no services. `kiosk-hardware_1.0.bb` installs:

- `kiosk-blacklist.conf` in `/etc/modprobe.d`: `raspberrypi_gpiomem`, `uio` and `uio_pdrv_genirq`
  are blacklisted and their `install` lines point at `/bin/true`. The blacklist keeps modules with
  no consumer here out of memory; it saves no boot time. `drm`, `backlight` and
  `drm_panel_orientation_quirks` must never be blacklisted: DRM is the display path.
- `watchdog.conf` in `system.conf.d`: `RuntimeWatchdogSec=14` arms `/dev/watchdog0` (the BCM2835
  hardware caps near 15 s); `RebootWatchdogSec` and `ShutdownWatchdogSec` are 30 s.
- `60-kiosk-panic.conf` in `sysctl.d`: `kernel.panic = 1` and `kernel.panic_on_oops = 1`.
- `60-kiosk-mglru.conf` in `tmpfiles.d`: writes `1000` to `/sys/kernel/mm/lru_gen/min_ttl_ms`, so
  memory thrash ends in a logged kernel OOM kill instead of a watchdog reset
  ([ADR 0003 rev 1](../../../docs/decisions/0003-oom-kill-through-mglru-min-ttl.md)).
- Masks (symlinks to `/dev/null`) for `zram.service` (the SysV script from the zram package, which
  is masked, not deleted), `systemd-resolved`, `systemd-logind`, `systemd-userdbd` (service and
  socket) and `getty@tty1`.
- A `getty@tty2` enable link, since with logind masked nothing starts a login on a console switch.
- Masks in `/etc/udev/rules.d` for each rule file named in `KIOSK_UDEV_RULES_MASKED`.

## How it fits

- The recipe is separate from a `systemd_%.bbappend` because changing systemd rebuilds WebKit.
- `kiosk-static-resolv.bbclass` points `/etc/resolv.conf` at `/data/config` once `systemd-resolved`
  is masked.
- `kiosk-recover` reverses the unit and udev masks and the resolver link on a running board.
- The kernel-command-line panic setting is in `kiosk-zero-w.yaml`; the sysctl here applies once
  userspace is up.

Part of [the device](../../../docs/device.md).

## Knobs

- `KIOSK_UDEV_RULES_MASKED` in the recipe: the udev rule files masked. `71-seat`, `73-seat-late`,
  `70-uaccess`, `60-drm`, `60-persistent-storage`, the net rules and the input rules
  (`60-input-id`, `60-evdev`, libinput) stay unmasked.
- `1000` in `60-kiosk-mglru.conf`: the `min_ttl_ms` threshold.
- `RuntimeWatchdogSec` in `watchdog.conf`: systemd pings at half this interval.
