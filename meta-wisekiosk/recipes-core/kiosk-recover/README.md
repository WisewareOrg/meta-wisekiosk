# kiosk-recover

`kiosk-recover_1.0.bb` carries `files/kiosk-recover`, a script that reverses `kiosk-hardware`'s
boot trims for a debugging session and reboots: it unmasks `systemd-resolved`, `systemd-logind`,
`systemd-userdbd` (service and socket), deletes the `/dev/null` symlinks in `/etc/udev/rules.d`,
and restores `/etc/resolv.conf` as a symlink to `/data/config/resolv.conf`. It is not a boot
un-bricker: it runs on a slot that already gives a shell.

## How it fits

- The recipe installs nothing. `tools/provision.sh` places the script on `/data` as
  `/data/RECOVER.sh`, so it survives an A/B flip and a reflash.
- `zram.service` stays masked: unmasking restores a unit that fails at every boot.
- It touches neither `/boot`, sshd, networkd nor `wpa_supplicant`, and runs only by hand.

Part of [the device](../../../docs/device.md).

## Knobs

- `kiosk-recover --dry-run` prints each change and makes none; no argument applies them. It is
  idempotent.
