# Reset 6 analysis: the batch-8 baseline's first `bench test` attempt

Bench board only, read-only except the pstore mount (mounted read-only, copied, unmounted;
nothing deleted). No reboot, no install, no sysctl write performed by this analysis itself --
the install that reset the board was `bench test`'s own `target_suite` run, not a manual action.
One board session (`reset6-remote-read.sh`), plus the pstore read described below. Address and
MAC are redacted to `<BENCH_ADDRESS>` and `<BOARD_MAC>`.

## Context

This reset happened during batch 8's pre-change perf baseline: `bench test
59969986d739e999652906f32c8ac9701624a926` on the current, un-modified HEAD -- before the
soft-lockup kernel fragment existed, before loop8.sh existed, with **no heartbeat and no
diagnostic sysctls armed**. Confirmed from the board directly: `hung_task_timeout_secs=120`
(the image default, not batch 5/6/7's `10`), zero `hb245` processes. This limits what can be
read from it relative to resets 2-5: there is no PID1/watchdog instrument, so unlike reset 5
this reset cannot be tested against the PID1-starvation question at all.

## What happened

- **Record:** `records/20261102T050109Z`, test commit `59969986d739e999652906f32c8ac9701624a926`,
  `exit_status` 90.
- **Install progress at the stop:** last rauc line " 92% Copying image to rootfs.1" -- in the
  80-99% range resets 2-4 died in, not reset 5's early ~26%.
- **Capture markers** (`tools/kiosk-install.sh`'s own shipped streams, which run on every
  install regardless of any loop's diagnostics): `[stats]` last sample at 00:05:46.54, then
  silence; `[kernel]`/`[stats]` sessions ended 00:05:53.66, `[journal]` at 00:05:54.66 -- a
  ~7.1 s gap from last data to the ServerAlive timeout firing, the same signature as resets 2-5.
  `capture stopped` lands at 00:10:45.74, a further ~4m51s later -- the same long
  session-ended-to-capture-stopped gap reset 5 showed (374 s window there; 468 s here), not a
  new anomaly.
- **Reset-cause register:** `rsts: 00000020` -- `HADWRF` (watchdog full reset) set, `HADPOR`
  clear. The fifth consecutive checked reset to read this value (n = 5 of 5: resets 2-6).
- **pstore:** `console-ramoops-0` only, 307 lines, md5 `62463305fad93d37b64e98cfeb6529e2`. No
  `dmesg-ramoops-*` -- expected, since the soft-lockup detector this investigation is about to
  add is not yet built into this kernel. The last 20 lines are rauc/kernel audit log lines
  (`DM-VERITY`/`installer` syscall audit records from the in-progress install), not a heartbeat
  -- none was armed. The boot this record came from (`boot_id ccfd7c10...`, the same boot reset
  5's own analysis names) ran for ~71768 s (~19.9 h) before this install reset it; nothing in
  that long idle stretch is of interest to this reset.
- **Recovery:** `rauc status` after the reset shows `Booted from: rootfs.0 (A)`, `Activated:
  rootfs.0 (A)`; `fw_printenv` shows `BOOT_ORDER=A BOOT_A_LEFT=3 BOOT_B_LEFT=0`. The fallback
  worked as designed, as at every prior reset.
- **Unchanged from the image default, confirmed directly:** `scheduler=none [mq-deadline] kyber
  bfq` (default, no BFQ -- this is the unmodified baseline image), `cpufreq
  scaling_governor=ondemand`.

## Reading

This is the same freeze-then-watchdog shape resets 2, 3 and 5 show (RSTS 0x20, a multi-second
silent gap before the ServerAlive timeout, the board recovers cleanly on the fallback slot), at
a copy position squarely inside the 80-99% range resets 2-4 died in. Without a heartbeat this
reset cannot say anything new about *why* the board stops -- it is one more data point for *that
it does*, at a baseline rate consistent with the ~2.6% this investigation has measured since
batch 1 (now 4 resets in 115 baseline/default-elevator `bench test` runs run against this
checkout's own HEAD, 1-4 plus this one; batches 6-7's BFQ runs are a separate population, see
the Batch 6/7 sections). It does not change any standing finding in this README's Findings
section.

## Classes and revert

- **Board changes: none, so there is nothing to revert**, other than the pstore mount, which was
  read-only and has been unmounted. `reset6-remote-read.sh` and the pstore copy are the only
  board interactions; nothing was written, deleted, or rebooted by this analysis.
