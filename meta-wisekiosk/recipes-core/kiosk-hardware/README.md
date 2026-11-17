# Out-of-memory behaviour in `kiosk-hardware`

`60-kiosk-mglru.conf` writes `1000` to `/sys/kernel/mm/lru_gen/min_ttl_ms` at boot through
`tmpfiles.d`. What ships in the image belongs in `kiosk-hardware_1.0.bb`; this file is why that one
setting exists and what was set aside for it.

## What it does

With multi-generation LRU, `kswapd` — a kernel thread userspace starvation cannot stop — compares
the age of the oldest file-page generation with `min_ttl_ms`. A generation younger than that means
the working set is being evicted faster than the limit allows, and the kernel calls
`out_of_memory()` (`mm/vmscan.c`, `lru_gen_age_node()`; `Documentation/admin-guide/mm/multigen_lru.rst`,
"Thrashing prevention").

Without it, memory exhaustion on this board is a thrash, not a kill: code pages refault from the SD
card and anonymous pages compress into zram, and both count as reclaim progress, so the ordinary OOM
killer never runs. PID 1 is starved, misses the 14 s hardware watchdog ping, and the SoC resets with
no kernel message. With it, the thrash ends in a kill the kernel logs at `pr_err`, which reaches the
journal and, across a reset, pstore's console record. The browser and backend both carry
`Restart=always`, so the panel comes back by the browser-killed path.

## Why 1000

The value is the one the kernel document names. Seeds on the board (#257 performance baseline) show that an anonymous
hog is killed and logged with no reset, and that an unkillable tmpfs hog produces a kill loop — about
one kill every 16 s, no reset — until the files are removed.

## What was set aside

- **`vm.panic_on_oom=1` with pstore:** acts only once the OOM killer is invoked, and under thrash the
  hang comes first.
- **earlyoom:** userspace, so the same starvation reaches it, and it keys on available memory and
  swap, which cannot see file-page thrash.
- **systemd-oomd:** needs systemd's `PACKAGECONFIG` changed, which rebuilds WebKit, and PSI enabled
  on the shared `/boot` command line, which an OTA cannot reach.
- **zram or swap sizing:** moves when the thrash starts, but does not stop it.
- **Hung-task or soft-lockup tuning:** neither fires inside the 14 s watchdog window.
