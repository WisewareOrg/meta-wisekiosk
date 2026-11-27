# kiosk-timesync-persist

`kiosk-timesync-persist_1.0.bb` installs `kiosk-timesync-dir.service` and a drop-in,
`10-persist-clock.conf`, for `systemd-timesyncd.service`. The oneshot creates
`/data/systemd-timesync` owned by `systemd-timesync` before timesyncd starts; the drop-in
`BindPaths=` that directory onto `/var/lib/systemd/timesync`, so timesyncd's saved clock lives on
`/data`.

## How it fits

- timesyncd restores the saved clock within seconds of starting, long before NTP sync, so a slot an
  update has just written boots with a real clock; why that matters is
  [`docs/updates.md`](../../../docs/updates.md) §"What a new slot carries".
- timesyncd runs under `ProtectSystem=strict`, so the directory is bound with `BindPaths=`; a write
  through a symlink to `/data` fails read-only. The leading `-` skips the bind when the source is
  missing, so a `/data` failure degrades to a non-persistent boot.
- timesyncd pulls the stager in with `Wants=`, so a failed stage leaves NTP running. The stager has
  no `RemainAfterExit=`, so it runs again at every timesyncd start.

Part of [the device](../../../docs/device.md).
