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
- The drop-in uses `BindPaths`, not a symlink: timesyncd runs `ProtectSystem=strict`, so a write
  through a symlink outside its sandbox fails read-only. The leading `-` skips the bind when the
  source is missing, so a `/data` failure degrades to a non-persistent boot.
- The stager is a `Wants=` of timesyncd, not `Requires=`, so a failed stage does not cancel NTP; it
  re-runs at each timesyncd start, so it is not `RemainAfterExit`.

Part of [the device](../../../docs/device.md).
