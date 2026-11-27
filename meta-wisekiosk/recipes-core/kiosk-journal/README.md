# kiosk-journal

`kiosk-journal_1.0.bb` keeps the systemd journal on `/data`, so a failed A/B update leaves its logs
behind. It installs:

- `99-kiosk-journal.conf` (`tmpfiles.d`): creates `/data/log` and `/data/log/journal` (group
  `systemd-journal`) and links `/var/log/journal` to the latter.
- `persistent.conf` (`journald.conf.d`): `Storage=persistent`, `SystemMaxUse=64M`,
  `SystemMaxFileSize=8M`.
- `kiosk-journal-flush.service`: a oneshot that runs `journalctl --flush` after
  `systemd-tmpfiles-setup.service` and journald, with `/data` mounted, to move the volatile journal
  into the persistent one.

## How it fits

- The recipe does not set `VOLATILE_LOG_DIR`: that variable is read by systemd's `do_install`, so
  setting it rebuilds systemd and everything depending on it, WebKit included.
- The flush is its own unit; an `After=systemd-tmpfiles-setup.service` drop-in on
  `systemd-journal-flush` makes an ordering cycle that deletes the tmpfiles job.
- The `L` line in the tmpfiles file takes four dashes before the target; a fifth is read as the Age
  field and breaks the link.

Part of [the device](../../../docs/device.md).

## Knobs

- `SystemMaxUse` and `SystemMaxFileSize` in `persistent.conf`: the cap must stay well above the
  working set, because journald drops early-boot entries when it runs out of free space, and the
  flush time scales with the journal's current size.
