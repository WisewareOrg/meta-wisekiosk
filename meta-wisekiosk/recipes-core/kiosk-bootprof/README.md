# kiosk-bootprof

A boot profiler: a small C sampler (`files/kiosk-bootprof.c`, built by `kiosk-bootprof_1.0.bb`) and
an analyzer (`files/analyze-boot-cpu-io.py`). From early boot the sampler reads `/proc/stat`,
`/sys/block/mmcblk0/stat`, `/proc/loadavg` and `/proc/modules` on an absolute `CLOCK_MONOTONIC`
grid and writes `/data/boot-cpu-io.<boot_id>.txt` once at the end. The analyzer turns that file
into per-window CPU and I/O figures. The recipe deploys the binary beside the image and never
installs it into the rootfs.

## How it fits

- `just bootprofile` (`justfiles/device.just`) runs the whole cycle through
  `tests/diagnostics/test_boot_profile.py` on the board `LG_ENV` names: copy the binary and the
  unit onto the board, enable, reboot, wait out the observer window, pull the samples and the
  matching journal, run the analyzer. The unit's `ExecStopPost=` removes the binary and the unit
  when it stops.
- The analyzer reads the journal (`-o short-monotonic`) for phase edges: wlan0 expected, local
  filesystems, basic system, wlan0 found, network online, kiosk browser started.
- The output header carries the sampler's own CPU cost (`self_cpu_us`) and the count of samples
  that missed their grid slot (`late`). `#M` lines list each kernel module with the time it first
  appeared in `/proc/modules`.

Part of [the measurement tools](../../../docs/testing.md).

## Knobs

- Sampler arguments: `kiosk-bootprof [duration_s [interval_ms [out_path [dev]]]]`, defaults 150 s,
  1000 ms, `/data/boot-cpu-io`, `mmcblk0`.
- `analyze-boot-cpu-io.py <sample-file>...` reads `<name>.journal.txt` beside each sample file.

## Reading a profile

- A long window means the single core is busy (work), waiting (`iowait %`, `rd_ms`/`wr_ms`) or
  queued behind unrelated work (run queue above one). The three have different fixes; overlapping
  phases helps only where the core idles during one of them.
- The sampler counts itself: `nr_running` includes it, so the analyzer reports run queue as
  `nr_running - 1`.
- `io_ticks` is not populated by this kernel's mmc driver; read `iowait %` and `rd_ms`/`wr_ms`.
- The samples start when the sampler's unit starts, so the kernel and early-systemd window is not
  covered.
- `/proc/pressure` does not exist (`CONFIG_PSI` is off) and `systemd-analyze` is not on the image.
- An instrumented boot runs longer in wall-clock than an uninstrumented one; compare profiled boots
  with profiled boots.
- One SSH connection costs the board's single core several seconds of CPU. Open one connection per
  boot, after the observer window, never a session left attached across it. Before about 30 s the
  board has no network, so `mmc1`, `brcmfmac`, `wlan0` and `Reached target Network is Online` are
  read from the journal later and are unaffected by a late connection; the browser start is not.
