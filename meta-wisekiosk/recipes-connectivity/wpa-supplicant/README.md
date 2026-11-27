# wpa-supplicant

Replaces the Wi-Fi unit with one that reads its configuration from `/data/config/wpa_supplicant.conf`.
`files/wpa_supplicant.service` runs `wpa_supplicant -i wlan0 -B` after and requiring `data.mount`, and
only when `/data` is a mount point. `files/robust.conf` is installed as a drop-in that orders the unit
after `sys-subsystem-net-devices-wlan0.device` and sets `Restart=on-failure`, `RestartSec=5`.
`wpa-supplicant-service.bbappend` wires both in.

## How it fits

- `FILESEXTRAPATHS:prepend` puts this layer's `files/` ahead of the upstream recipe's, so its
  `SRC_URI = "file://wpa_supplicant.service"` resolves to this layer's unit.
- `do_install:append` rewrites the bare `ExecStart=wpa_supplicant` to `${sbindir}/wpa_supplicant`;
  systemd requires an absolute path.
- The unit is `Type=forking`; the drop-in's wlan0 ordering covers a start before brcmfmac has created the
  interface, and `Restart` covers an exit after that.
- The SSID and PSK hash are site configuration written to `/data/config` by provisioning; the image
  carries none.

Part of [the device](../../../docs/device.md).

## Knobs

- `Restart=`, `RestartSec=`: `files/robust.conf`.
- Configuration path: `ExecStart` in `files/wpa_supplicant.service`.
