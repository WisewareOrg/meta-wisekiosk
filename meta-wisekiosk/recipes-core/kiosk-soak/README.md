# kiosk-soak

`kiosk-soak_1.0.bb` installs `/usr/bin/kiosk-soak.sh`, a oneshot `kiosk-soak.service` and
`kiosk-soak.timer`. The timer (enabled in `timers.target`) runs the sampler 5 minutes after boot and
every 5 minutes after, with `AccuracySec=1s`. Each run appends one `key=value` line to
`/data/kiosk-soak.log`: boot id, uptime, load, temperature, throttle flags, memory, disk, and the
browser's pid, process count and RSS (the whole `kiosk-browser` and `WPE*` family, because the
renderer holds most of the memory). The log is capped at `KIOSK_SOAK_MAXLINES` lines.

## How it fits

- The log lives on `/data`, so it survives an A/B update.
- `kiosk-soak.sh --summary [N]` reports over the last N samples: reboots, browser restarts, gaps,
  samples without a browser, RSS range, slope, peak temperature and load, throttled samples.
- The summary's endpoint delta is not a rate: the first sample may simply be the lowest. One line
  fitted through a step reports the step as a rate, and flat stretches either side of a step mean
  the working set grew, not that memory leaks. Judge a leak by comparing samples taken at matched
  page states far apart.

Part of [the device](../../../docs/device.md).

## Knobs

- `KIOSK_SOAK_LOG` (default `/data/kiosk-soak.log`) and `KIOSK_SOAK_MAXLINES` (default 20000).
- `OnBootSec` and `OnUnitActiveSec` in `files/kiosk-soak.timer`: the sample cadence.
