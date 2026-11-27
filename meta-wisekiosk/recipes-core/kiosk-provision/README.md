# kiosk-provision

`kiosk-provision_1.0.bb` installs `kiosk-provision`, `kiosk-seed-config` and
`kiosk-provision.service`. The image carries no site configuration; the service runs once at boot
(`WantedBy=sysinit.target`, after `data.mount`, before `wpa_supplicant`, `systemd-timesyncd`,
`kiosk.service` and `network-pre.target`) and:

- logs `ok` or `MISSING` for `wpa_supplicant.conf`, `kiosk.conf` and `resolv.conf` under
  `/data/config`, and `UNPROVISIONED` when any is missing;
- sets the hostname from `/data/config/hostname`, kernel and `/etc/hostname`;
- copies the rootfs's `/etc/machine-id` to `/data/etc/machine-id` when `/data` has none;
- runs `kiosk-seed-config`, which copies `/usr/share/wisekiosk/config.example.json` to
  `/data/config/config.json` only when no `config.json` exists.

It always exits 0.

## How it fits

- `wpa_supplicant`, `kiosk.service` and `/etc/resolv.conf` read `/data/config` directly; they need
  nothing from this script.
- The machine-id cannot be applied here: journald reads it before `/data` is mounted. A RAUC
  slot-post-install hook writes it into the new slot from `/data/etc/machine-id`.
- An unprovisioned board has no network; recovery is a USB keyboard on tty2.

Part of [the device](../../../docs/device.md).

## Knobs

- `/data/config/{wpa_supplicant.conf,kiosk.conf,resolv.conf,hostname,config.json}`: the site files.
- `ROOT` in `kiosk-seed-config` relocates every path it touches, for tests; a real boot leaves it
  empty.
