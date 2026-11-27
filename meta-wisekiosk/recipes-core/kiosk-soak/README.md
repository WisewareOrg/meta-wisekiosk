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
- The script's header documents each field of a log line.

Part of [the device](../../../docs/device.md).

## Reading a long run

Read a `--summary` in this order, weakest evidence last:

1. Reboots and browser restarts: a non-zero count means the memory series is really two series.
2. Samples without a browser: the kiosk was down at those samples.
3. The shape of `rss_total` across the window, read against the log.
4. The slope, last. The summary's endpoint delta is not a rate — the first sample may simply be the
   lowest — and one line fitted through a step reports the step as a rate. Flat stretches either
   side of a step mean the working set grew, not that memory leaks; a leak is judged by comparing
   samples taken at matched page states far apart.

## Knobs

- `KIOSK_SOAK_LOG` (default `/data/kiosk-soak.log`) and `KIOSK_SOAK_MAXLINES` (default 20000).
- `OnBootSec` and `OnUnitActiveSec` in `files/kiosk-soak.timer`: the sample cadence.
