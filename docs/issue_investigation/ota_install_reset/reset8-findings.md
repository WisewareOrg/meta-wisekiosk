# Reset 8 analysis: batch-9 (loop9c) run 17 (#245 mid-install hard reset, first reset under the `watchdog_thresh=1` detector)

Bench board only, read-only. Nothing on the board was changed: no reboot, no install, no mount, no
/boot write, no sysctl write, no pstore access (`loop9c.sh` had already copied and unmounted it;
`grep -c pstore /proc/mounts` = 0). Prod was not contacted. `~/meta-wisekiosk`'s git state was not
touched. Three read-only board sessions, each
`flock -o -w 900 ~/wisekiosk-bench/records/lock ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@<BENCH_ADDRESS> sh -s < <script>`:
`reset8-remote-read.sh` (16:02:26–16:02:46 host, every line host-stamped), `reset8-remote-read2.sh` (which
driver binds each mmc host) and `reset8-remote-read3.sh` (the soak timer and its run times, ~16:12).
Address, hostname and MAC appear here as `<BENCH_ADDRESS>`, `<BENCH_HOSTNAME>`, `<BOARD_MAC>`.

- **Record.** `records/20261102T205017Z`, test commit `3bd3e8a9fc54`, `exit_status` 90.
  `loop9c/summary.txt`: `15:59:08 run=17 … exit=2 record=records/20261102T205017Z reset=yes panic=no voided=no`.
  Runs 1–15 clean; run 16 voided (`exit=1 record=none`: host_suite failed before any install).
- **Run 16 did not touch the board's boot.** `journalctl --list-boots`: boot −1 spans 15:44:00 →
  15:53:56, i.e. from run 15's post-install reboot to run 17's reset, with no boot in between.
- **pstore copy.** `console-ramoops-0`: 745 lines, 131 060 B (ring wrapped; first whole line
  `[264.7]`), md5 `6be56f5cb84a6fdb1f4b83939168b5d1`. `dmesg-ramoops-0`: 23 978 B, sha256
  `4761212a…`, **the carried-over sysrq seed** (`Panic#1`, `sysrq: Trigger a crash` at [464.08]).
- **Scripts and raw outputs** are in
  `/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/reset8/`:
  `final30.py` (reset 7's, path changed) → `final30.out`; `timing8.py` (timing7's method, see §3)
  → `timing8.out`; `detect8.py` (detect7's model at thresh=1) → `detect8.out`; `latency8.py`,
  `hung8.py`, `episodes8.py`, `load8.py`, `lull8.py` → `*.out`. The committed `extract.py`,
  `stamp.py`, `progress.py` and `metrics.py` were run unchanged (`progress-b9c.txt`,
  `b9c-metrics.txt`, over all 16 loop9c records). `.out` files are unredacted except
  `stdout.redacted`.
- **Clocks.** Host EST unless marked *board* or *printk*.
  - Host = board + 0.003 s: the minimum of receive minus board stamp over the 606 `[kernel]`
    heartbeat lines.
  - printk zero of boot −1 = board 15:44:06.407 (from `[600.823]` = board 15:54:07.229944, the
    last heartbeat present in both pstore and the host stream).

## Verdict

1. **This stop came early in the pet cycle, so the stop → reset window was long: ~11.9–12.5 s
   (≥ 11.4 s on the most conservative bound).** The last pet was at printk 599.2–599.7; the board
   was alive at 601.37 and silent by ~601.9; the hardware watchdog reset it 14 s after that pet, at
   ~613.8. This is reset 5's geometry, not reset 7's.
2. **The `watchdog_thresh=1` detector needed at most 3.55 s after the stop (model, from 6.12.93
   source). It had ≥ 7.9 s of slack, enough for any dump time up to 5 s. Modelled P(record lands
   before the reset) = 1.000 in every case.** Reset 7's "the detector raced the watchdog" caveat does
   not apply: even the old thresh=3 (≤ 8.4 s) would have fitted.
3. **Nothing printed.** pstore ends on an ordinary heartbeat (`[601.374] … wdt=12 p1=S
   p1wchan=do_epoll_wait`). There is no soft-lockup, `BUG:`, panic, oops, RCU, sdhost or
   mmc-timeout line. **No new `dmesg-ramoops` record**: the only one is the seed, byte-identical
   in all 16 loop9c records, so `panic=no` is correct.
4. **The detector was armed on the boot that reset.** That is the 17th of 17 `kernel.watchdog_thresh
   = 1` readbacks in `loop9c/LOG`, placed on boot −1 by the pstore heartbeat series (§2).
5. **Two other kernel witnesses had time and were also silent.**
   - The khungtaskd series: the `mmc_rescan` kworker had been reported every 2.07–2.09 s for
     33 s. Its next report was due at ~[603.0], and five more before the reset. In healthy loop9c
     runs, 13 of 14 such episodes that reached 33 s were reported again.
   - The SD driver's 10 s command timeout.
6. **Ruled out, strongly, conditional on the detection half working as the source says:** any
   interrupts-on kernel lockup, meaning the CPU taking timer interrupts while no SCHED_NORMAL task
   (the touch kworker, PID1, the heartbeats) ran for > 2 s.
   - This condition matters because the detection half has never been seeded on this board.
   - **Argued against (moderate–strong):** a live kernel under a silent userspace-only or SD stall.
7. **What remains:** the CPU stopped taking the timer interrupt at the stop and never took it again.
   - **(a) Still executing, with IRQs masked:** an IRQs-off loop or hang in a driver or core path, a
     hard-IRQ handler that never returns, or an IRQ storm starving the timer IRQ.
   - **(b) Not executing:** a load/store to a peripheral that never completes (an AXI/APB stall),
     or an SoC-level clock, SDRAM or rail fault.
   - The next diagnostic that separates (a) from (b) is in §5.

## 1. Final heartbeats (pstore and host `[kernel]` stream)

**Two heartbeat processes ran in boot −1.** Run 16 armed `hb245` and was voided without a reboot.
Run 17 armed a second one.
- The two series interleave at ~0.6 s, from printk ~268.6 to the end.
- loop9c run 1 had the same doubling after loop9b's crash (324 window heartbeats) and was clean, so
  it is not unique to this run.

**pstore vs host.**
- pstore holds 514 heartbeats; the host stream holds 606, because `dmesg -w` replayed boot history.
- **pstore-only: exactly one, the last** (`601.22`, printk 601.374). Host-only: 5 early ones from
  before pstore's ring start.
- The hung-task report at [600.963] reached the host (`[kernel]` at 15:54:07.399), and so did the
  journal up to board 15:54:07.387.
- **pstore holds one more line than the host ever got.**

dR and dWs are reads completed and write sectors, as deltas since the previous heartbeat.
`p1majflt` is 143 in every row; `uv=0 freq=900000` in all 515 pstore samples.

| host recv | printk | uptime | wdt | p1 | p1wchan | load1 | Dirty kB | WB kB | dR | dWs |
|---|---|---|---|---|---|---|---|---|---|---|
| 15:54:02.189 | 595.764 | 595.39 | 10 | S | do_epoll_wait | 4.77 | 10364 | 39728 | 0 | 15360 |
| 15:54:02.917 | 596.496 | 596.00 | 10 | S | do_epoll_wait | 4.77 | 9900 | 38912 | 0 | 18048 |
| 15:54:03.707 | 597.290 | 596.79 | 9 | S | do_epoll_wait | 4.94 | 11280 | 35076 | 0 | 25600 |
| 15:54:04.366 | 597.951 | 597.52 | 8 | S | do_epoll_wait | 4.94 | 3324 | 44852 | 0 | 12288 |
| 15:54:04.991 | 598.566 | 598.31 | 8 | S | do_epoll_wait | 4.94 | 6408 | 40760 | 0 | 24576 |
| 15:54:05.495 | 599.073 | 598.95 | 7 | S | do_epoll_wait | 4.94 | 4424 | 40760 | 0 | 14336 |
| 15:54:06.117 | 599.697 | 599.57 | **13** | S | do_epoll_wait | 4.94 | 4432 | 32056 | 0 | 18432 |
| 15:54:06.625 | 600.210 | 600.08 | 13 | S | do_epoll_wait | 4.94 | 4444 | 22328 | 0 | 19456 |
| 15:54:07.251 | 600.823 | 600.70 | 12 | S | do_epoll_wait | 4.94 | 4448 | 16184 | 0 | 12288 |
| **never received** | **601.374** | **601.22** | **12** | **S** | **do_epoll_wait** | 4.95 | 4484 | 11576 | 0 | 9216 |

The full 40-row table is in `final30.out`.

- **wdt and PID1.**
  - The last pet came between the wdt=7 sample at [599.07] and the wdt=13 one at [599.70]. That
    was 1.7–2.2 s before the last heartbeat.
  - `metrics.py`: `min_wdt=7` in all 16 loop9c runs. PID1 was `S` in 513 of 515 samples (2 `R`),
    `p1_d_seconds=0.0`, never `D`.
- **Load** was 4.95 at the end. The install-window maximum was 4.94–4.95, against healthy loop9c
  maxima of 5.42–9.51 (n = 15, `load8.out`). This run died ~85 s before the healthy runs' ends, so
  read that as low or ordinary, not as a signal.
- **Dirty/Writeback.**
  - Dirty sat flat at ~4.4 MB from [599.07] to the end (2.3 s) while Writeback drained from 40.8
    to 11.6 MB.
  - Healthy loop9c runs show the same flat-Dirty lull, with the longest stretch per run 1.22–2.63 s
    (n = 15, `lull8.out`). Run 17's own longest stretch, 2.51 s, came earlier, at uptime 493.
  - **No precursor.**
- **Copy progress.**
  - The last rauc line was ` 72% Copying image to rootfs.0`.
  - 2 063 618 sectors were written by +119.6 s after `capture started`. That is ~49% of a full
    copy (~4.21 M sectors).
  - Healthy loop9c runs reach the same volume at 111.9–150.3 s (n = 15), so the run was **on
    schedule**.
  - Copy positions at reset are now 80/84/90/99/26/92/56/49% (resets 1–8, as each analysis
    reported them). The units are mixed: the early figures are rauc's percentage, the later ones
    are bytes. Either way the resets are spread across the write window.
- **Heartbeat gaps.** `metrics.py` `max_hb_gap=6.62`, at [489.3], the install's start (bundle
  check). Healthy loop9c values are 1.64–7.48 s, so this is ordinary.
- **Host side.**
  - Last arrivals: `[stats]` 15:54:06.955, `[kernel]` 15:54:07.401 and `[journal]` 15:54:07.581.
  - "not responding" followed at 15:54:14.21 / 15:54:15.21 / 15:54:15.21: the ServerAlive
    signature, as in resets 2–7.
  - The `[stats]` sample due at ~15:54:08.05 (cadence ~1.1 s) never arrived.

## 2. Detector strings in pstore, and was the detector armed

**pstore console.**
- Case-insensitive grep for `soft lockup|BUG:|Kernel panic|rcu|watchdog|hung|lockup|stall|Oops|sdhost|mmc[01]:|error|timeout|brcmf|reboot`.
- The only hits are the 12 routine `INFO: task kworker/0:2:5034 blocked for more than 10…33
  seconds` reports (`mmc_rescan` → `__mmc_claim_host`), from [578.08] to [600.96] at 2.07–2.09 s
  spacing.
- The ring wrapped, so boot-time lines are not in this copy.
- `CONFIG_TINY_RCU=y`, so there is no RCU stall detector and the absence of "rcu" says nothing.

**dmesg-ramoops, checked against the manifest logic.**
- `loop9c.sh` replaces its reference manifest only after a run that produced a record. Run 16
  produced none, so run 17 was compared against **run 15's** manifest.
- The `dmesg-ramoops-0` sha256 `4761212a…` is the same in runs 1–17, and the file is the sysrq
  seed (`Kernel panic - not syncing: sysrq triggered crash`).
- **No `dmesg-ramoops` record is new or changed.** Only `console-ramoops-0` differs, as it does
  on every boot.

**Was the detector armed on the boot that reset? Yes.**
- **LOG.** There are 17 `kernel.watchdog_thresh = 1` readbacks and 17 hung-task arming triples,
  one per run including the voided run 16. There is no `FAIL` and no `loop9c: failed` line.
  - The only error is the known `printk_devkmsg` "Invalid argument" every run (logged and skipped
    by design).
- **Placed on boot −1.**
  - `set_lockup_thresh` runs before `arm_diagnostics` (which starts `hb245`) under `set -e`.
  - Boot −1's pstore holds a first heartbeat series from run 16's arming, and a second one
    starting at printk ~268.6 (board ~15:48:35), seconds after run 16's summary line at 15:48:30.
    That second series is run 17's arming.
  - So readbacks 16 and 17 both wrote `thresh=1` into boot −1, and no reboot intervened (list-boots).
- **The hung-task arming took effect in boot −1** (2 s report spacing).
- **Same kernel.**
  - Boot −1's command line (from the host `[kernel]` backlog) has `panic=10 rauc.slot=B` and no
    `nowatchdog`, `nosoftlockup`, `watchdog_thresh=` or `softlockup_panic=`.
  - The build string `#1 Fri Jun 12 11:45:31 UTC 2026` matches the current boot's `uname`.
  - The install ran from `rootfs.1 (B)` and targeted `rootfs.0`.
- **Current boot (same kernel):** `watchdog=1 soft_watchdog=1 softlockup_panic=1 nmi_watchdog=0
  watchdog_thresh=10` (reverted at reboot, as designed), `panic=10 panic_on_oops=1 tainted=0`.
  ramoops has `max_reason=2 record_size=32768 console_size=131072 ftrace_size=0`.
- **Built config** (`build/…/linux-raspberrypi/6.12.93+git/…/.config`, mtime 00:53 today):
  `CONFIG_SOFTLOCKUP_DETECTOR=y`, `CONFIG_BOOTPARAM_SOFTLOCKUP_PANIC=y`, `CONFIG_PREEMPT_VOLUNTARY=y`,
  `CONFIG_HZ=100`.

**How a report would reach pstore.** From 6.12.93 source; not exercised for a soft lockup.
- `watchdog_timer_fn` is a `HRTIMER_MODE_REL_HARD` hrtimer, so it fires in hard-IRQ context
  whenever IRQs are on.
- It prints `BUG: soft lockup` under `printk_cpu_sync_get_irqsave`. That makes
  `is_printk_legacy_deferred()` true, so the console flush is deferred while the sync is held.
- Then `panic()` runs `kmsg_dump` (→ `dmesg-ramoops`) and `console_flush_on_panic`.
- The sysrq seed proved panic → `dmesg-ramoops` from process context. Hard-IRQ context is the same
  `panic()` path, but that was not exercised.

## 3. Timing: last pet, stop window, reset

**Clocks.**
- **K, kernel start of the current boot = 15:54:27.633 host.** This is the minimum of host-receive
  minus `/proc/uptime` over 20 samples (spread 0.229 s).
  - Cross-check: the `dmesg --time-format iso` head, board 15:54:27.625202, plus the offset gives
    15:54:27.628 (Δ −4 ms).
  - Last pstore heartbeat to K: **19.85 s.** Earlier resets: reset 7 15.09, reset 5 22.04.
- **F, measured fresh.** Boot −2 `Journal stopped` (board 15:43:59.022) to boot −1 printk zero
  (15:44:06.407) is **7.385 s**. That is inside the 7.32–7.43 s envelope (now n = 18). B ≤ F.
- **Observed reset (K − B, tail ~0):** printk **613.79–613.90**, host 15:54:20.20–20.31. If the
  shutdown tail is up to 1 s, the range extends to printk 614.90.

**Watchdog timing test.** Reset 5/7 method (`timing8.out`). P comes from intersecting the wdt
bounds since the last increase.

| scenario | k = 1.00 | k = 1.02 | k = 1.08 |
|---|---|---|---|
| last pet P | 599.22–599.70 | 599.18–599.70 | 599.06–599.70 |
| A: no further pet, reset at P + 14k | 613.22–613.70, miss +0.10 s | 613.46–613.98, **miss 0** | 614.18–614.82, miss 0 |
| B: one more pet (due P + 6.2…7.7 s) | 619.4–621.4, **miss −4.5 s** | −4.9 s | −6.0 s |

- **A fits.** The +0.10 s at k = 1 is inside the error budget: the F spread is 0.11 s, and the pet
  bound edges add more. **B is rejected**: the next pet was not due until ≥ 605.4, after the stop.
- **The reset agent is the hardware watchdog, expiring 14 s after the pet at ~599.5.** This is
  consistent with RSTS 0x20 (§4). An immediate reset at the stop would have put K ~7.4 s after the
  last heartbeat, not 19.9 s.

**The stop window.**
- **Alive at 601.374:** a heartbeat printed, and PID1 was `S do_epoll_wait`.
- **Silent soon after.** Three independent bounds:
  - **Delivery.**
    - The 601.374 heartbeat reached pstore but never reached the host. Over the 166 live heartbeat
      lines of this install window, delivery latency was 0.003–0.483 s (p50 0.016, p99 0.251;
      `latency8.out`).
    - So if the board's `dmesg -w` reader, sshd and network had stayed up, it would have arrived by
      ~601.86.
  - **`[stats]`.** The sample due ~15:54:08.05 (≈ printk 601.6) never came.
  - **Heartbeats.** The per-series interval in the last 12 samples was 1.13–1.52 s. The next
    heartbeat was due by ≤ 602.35 and never came.
- So **S ∈ [601.37, ~601.86]**, conservative upper bound 602.35.
- **Stop → reset = 11.93–12.53 s** (k = 1, tail ~0). Conservative: **11.44 s minimum**, 13.53 s
  maximum with a 1 s tail.

**Detector latency at `watchdog_thresh=1`.**
- **Mechanism (6.12.93 `kernel/watchdog.c`, re-read):**
  - sample period = `2·thresh/5` = 0.4 s;
  - `get_timestamp()` = `running_clock() >> 30` (1.074 s units);
  - the report fires when `time_after(now, period_ts + 2·thresh)`.
- **Monte Carlo** (`detect8.py`, the same model as detect7, 200 000 draws per case, S and R uniform
  in their windows, uniform hrtimer phase):

  | S window | R window | dump 0 / 0.5 / 2 / 5 s | latency after stop | min slack |
  |---|---|---|---|---|
  | 601.37–601.86 | 613.79–613.90 | P = 1.000 in all four | 2.00–3.55 s (median 2.96) | 8.38 s |
  | 601.37–602.35 | 613.79–614.90 | P = 1.000 in all four | 2.00–3.55 s (median 2.72) | 7.89 s |

- **Contrasts.**
  - On this geometry even thresh=3 gives P = 1.000 (max latency 8.40 s < 11.44 s).
  - thresh=1 on reset 7's geometry also gives P = 1.000.

**Answer to Q2: yes.** The window was longer than the worst-case 3.6 s plus any plausible dump time,
by ≥ 7.9 s. An interrupts-on soft lockup would have been caught with near certainty, *given that the
detector fires at all*. That proviso is the one unproven link (§5).

**Two further kernel witnesses that had time.**
- **khungtaskd.**
  - `kworker/0:2:5034` (`mmc_rescan`) had been in D for 33 s and was reported every 2.07–2.09 s.
    A live kernel reports it again at ~[603.04], then ~605.1, 607.2, 609.3, 611.4 and 613.5. None
    came.
  - **Base rate** (`episodes8.out`, loop9c runs 1–15): 54 hung-task episodes. 14 reached ≥ 33 s,
    and **13 of those 14 were reported again**.
  - So the series ending is ~13:1 evidence that the kernel stopped scheduling khungtaskd before
    ~603.
  - It is not independent of the soft-lockup evidence for the interrupts-on case, since khungtaskd
    is also a SCHED_NORMAL kthread. But it does bear on the live-kernel cases below.
- **SD command timeout.**
  - **Verified on the board:** `mmc0` (20202000.mmc) is bound to `sdhost-bcm2835`, which is
    `drivers/mmc/host/bcm2835.c` (`CONFIG_MMC_BCM2835=y`). `mmc1` (wifi) is bound to `mmc-bcm2835`.
  - `bcm2835_send_command` arms `schedule_delayed_work(&host->timeout_work, 10 * HZ)`. On expiry,
    `bcm2835_timeout` prints `timeout waiting for hardware interrupt.` and dumps registers.
  - A command outstanding at S would have printed by ≤ S + 10 ≈ 611.9 (≤ 612.4), before the reset
    at 613.8.
  - **Correction to resets 5 and 7.** They cite `bcm2835-sdhost.c`'s `mod_timer`. That file is not
    built (`# CONFIG_MMC_BCM2835_SDHOST is not set`). The 10 s and the message are the same, but the
    timeout is **workqueue-driven**, so it needs a running scheduler, not just the timer IRQ. Their
    conclusions are unaffected; this only names the mechanism correctly.

## 4. Current boot (read 16:02:26 host)

- **RSTS:** `rsts: 00000020`, `partition: 0`, `tryboot: 0`, `boot-mode: 1`.
  - HADWRF is the only bit set; HADPOR is clear (decode per `reset2-rsts-pstore.md` §1).
  - **7 of 7** checked resets (2–8) read 0x20. A panic-restart would also set HADWRF, but none
    happened: no dmesg record, and §3's timing.
- **uv:** `hwmon1 in0_lcrit_alarm=0`.
  - `uv=0` in all 515 pstore heartbeats and all 93 `[stats]` samples of the window.
  - No voltage or throttle line in dmesg. Thermal 47.1 °C.
- **rauc status.**
  - Booted `rootfs.1 (B)`, Activated `rootfs.1 (B)`.
  - `[rootfs.1]` (/dev/mmcblk0p3) booted and **good**. `[rootfs.0]` (/dev/mmcblk0p2) inactive
    and **bad**: the interrupted target.
  - `fw_printenv`: `BOOT_ORDER=B`, `BOOT_A_LEFT=0`, `BOOT_B_LEFT=3`. **The fallback worked as
    designed.**
- **Other state.**
  - Scheduler `none [mq-deadline] kyber bfq`, governor `ondemand`.
  - Hung-task sysctls are back at their defaults (120 / 0 / 10). `hb245` processes: 0.
  - watchdog0: `timeout=14`, `timeleft=12`, `bootstatus=0`. `RuntimeWatchdogUSec=14s`.
  - `sched_rt_runtime_us=950000`.
- **dmesg.**
  - `EXT4-fs (mmcblk0p3): recovery required … recovery complete`.
  - `FAT-fs (mmcblk0p1): Volume was not properly unmounted` at [14.58], /boot's dirty bit as in
    resets 4, 5 and 7. Neither of these is a write I made.
- **Journal.** Boot −1's on-disk journal ends at board 15:53:56.7, at heartbeat 587.96. That is
  ~11 s before the stop, which is ordinary flush lag. There are no non-heartbeat lines after
  15:53:00 except the hung-task reports.
- **Soak coincidence (noted, not a finding).**
  - `kiosk-soak.timer` is `OnUnitActiveSec=5min AccuracySec=1s`. In boot −1 it last started at
    board 15:49:06.86.
  - Its start-to-start spacing on this board is 300.98–302.92 s (n = 3, boots −2 and 0). So the
    next sample was **due at printk ~601.45–603.4, at or just after the stop window**.
  - The journal stream (delivered to board 15:54:07.387) shows no soak start, so it had not begun
    by then.
  - The script calls `vcgencmd get_throttled`, a firmware mailbox call, among plain /proc reads.
  - Against it mattering: resets 7 and 5 stopped 89 s and 164 s before their next soak sample, so
    the soak cannot be necessary for the reset. Most healthy installs overlap a soak sample.
  - Recorded so the next reset's soak phase gets checked. n = 1, post hoc.

## 5. Verdict detail and the next diagnostic

**Ruled out: any interrupts-on kernel lockup. Strong, conditional.**
- The touch that the detector checks is an ordinary `system_wq` kworker on this UP board. So any
  state where the timer IRQ is serviced but no SCHED_NORMAL task runs for > 2 s panics with a stack
  within 3.55 s. That covers:
  - a non-preemptible kernel loop (`PREEMPT_VOLUNTARY`, so a loop without `cond_resched`);
  - softirq or hard-IRQ handler monopolisation;
  - CFS starvation.
- **Inference, not measured:** the complementary interrupts-on case, where CFS still gets CPU time
  (an RT hog under the 95% throttle and the fair server, or a loop that calls `cond_resched`), would
  have let PID1 pet. Then there is no 14 s watchdog expiry at all, so it is not this reset either.
- **Strength.** Detection probability ≈ 1 against a 12 s window, likelihood ratio > 50 on any
  reasonable dump time. This is the strongest single exclusion the investigation has.
- **The condition.** The detection half has never been seeded on this board.
  - The sysrq seed proved only panic → pstore.
  - 73 clean thresh=1 installs show the detector does not fire falsely. They say nothing about
    whether it fires truly.
  - The CFS-starvation seed in `reset7-analysis.md` §5 would close this. It is a runtime-only
    debugfs and sysctl write that ends in one deliberate bench panic, so it is recoverable over the
    wire. It is the owner's call.

**Argued against (moderate–strong): the kernel stayed alive while the board went dark.**
- Userspace-wide stall: the khungtaskd series ending is 13:1, and nothing on a live kernel would
  freeze PID1, two shells and sshd at once with 74 MB free.
- SD controller wedged with a live kernel: the bcm2835 10 s timeout and the continued `mmc_rescan`
  reports would both have printed.
- Power: HADPOR clear, `uv=0` throughout, as in every earlier reset. This is only as strong as the
  ~0.6 s heartbeat and ~1.1 s stats sampling of a latched flag.

**What remains: the CPU stopped taking the timer interrupt at S and never took it again.**
- **(a) Executing with IRQs masked.**
  - An IRQs-off loop. A poll whose timeout counts `jiffies` is the classic case: jiffies never
    advance with IRQs off on UP.
  - A hard-IRQ handler that never returns.
  - An IRQ storm that keeps the BCM2835 controller dispatching another source ahead of the timer.
- **(b) Not executing.** A load or store to a peripheral that never completes (the SD host, DMA or
  another APB/AXI target holding the bus), or a clock, SDRAM or rail fault below the uv detector.
- **Every in-CPU software witness is blind to both.** The detector, khungtaskd, workqueue
  timeouts, printk and the network all need the timer IRQ or the scheduler. That is why seven
  resets have printed nothing.

**The single next diagnostic that separates (a) from (b): the persistent function tracer
(`CONFIG_PSTORE_FTRACE`), armed only for the install window.**
- **Why it separates the two.** It is the one listed instrument that keeps recording with IRQs
  masked.
  - `pstore_ftrace_call` writes `{ip, parent_ip, seq}` into the ramoops ftrace zone on every traced
    function entry, from any context. It only does `local_irq_save` internally.
  - So at the next reset, its ring shows one of two things:
    - **(a)** the last entries **cycling** through a fixed set of functions up to the reset. The CPU
      kept executing, and the set names the loop.
    - **(b)** the trace **ending on one call with no repetition**. The CPU stopped in or after that
      function.
  - The remaining ambiguity is an IRQs-off poll made only of inline MMIO, with no traced calls.
    That also looks like (b), but the final function then names the poller, and its source says
    whether it can loop.
  - `seq` is a counter, not a timestamp (verified in `fs/pstore/ftrace.c`), so "still running"
    shows as repetition, not as elapsed time.
- **Why not the irqsoff tracer.** `CONFIG_IRQSOFF_TRACER` records a section's latency when IRQs
  are *re-enabled*, so a section that never ends is never recorded. In healthy runs it would map
  the longest IRQs-off sections and their call sites, which is useful for ranking candidates for
  (a). But it cannot observe the fatal event, so it cannot separate (a) from (b). It also needs a
  kernel rebuild (`# CONFIG_IRQSOFF_TRACER is not set`).
- **What pstore ftrace costs, and its class.**
  - **Kernel rebuild with `CONFIG_PSTORE_FTRACE=y`.**
    - The prerequisites are present: `CONFIG_FUNCTION_TRACER=y`, `DYNAMIC_FTRACE=y`,
      `DEBUG_FS=y`; `# CONFIG_PSTORE_FTRACE is not set`.
    - It ships by OTA into the slot. Recoverable, because the other slot keeps the old kernel.
  - **An ftrace zone in ramoops.** It is 0 today, and **the rpi `ramoops` overlay exposes only
    `base-addr`, `total-size`, `record-size` and `console-size`, with no `ftrace-size`**
    (checked in `arch/arm/boot/dts/overlays/ramoops-overlay.dts`). So the zone cannot come from a
    `config.txt` parameter. That route would also be a shared-/boot write, the hands-on class.
    - The recoverable route is a small kernel patch in `fs/pstore/ram.c`'s DT parse. It would set
      a nonzero `ftrace-size` when the DT gives none, inside the existing 256 KiB reservation: for
      example 64 KiB taken from the 128 KiB dump zone, which leaves 2 × 32 KiB panic records. That
      stays in the slot kernel.
  - **Runtime arming, per run.** `echo 1 > /sys/kernel/debug/pstore/record_ftrace` plus a
    `set_ftrace_filter` (mmc, bcm2835 SD and DMA, IRQ entry, wdt) to bound the overhead. This
    reverts at reboot. `loop9c.sh`'s `save_pstore` already copies every pstore file, so it would
    pick up `ftrace-ramoops-0`.
- **Risks.**
  - Every traced call is an uncached 16-byte write with IRQs saved, so it perturbs exactly the
    timing a 2.6% hazard might depend on. A narrow filter limits that, but can also miss the loop.
  - It is image content. The owner's batch-8 ruling (detector in the main image if it does not hurt
    performance) and the "no test content in the image" rule both bear on it, so it needs the same
    perf check batch 8 did.
- **Definitive but hands-on alternative, noted and not recommended:** JTAG on GPIO 22–27. It needs
  `enable_jtag_gpio=1` in shared `config.txt` plus wiring an adapter.
  - My understanding, **not verified** for the ARM1176: a halt request is taken at an instruction
    boundary. A core stalled on a never-completing bus transaction would fail to halt, which is
    (b). A core that halts with `CPSR.I=1` and its PC in a loop is (a).
- **Lean, a decision for the owner.**
  1. First, the CFS-starvation seed: cheap, runtime-only, one bench panic. It turns the
     interrupts-on-lockup ruling above from conditional to unconditional.
  2. Then pstore ftrace through the in-kernel zone patch, perf-checked, under the same loop.

## Overall tally (resets under capture, per install)

Counted from the README run table, the loop summaries, and this record.
- **Installs counted:** each `rauc install` that ran.
- **Not counted:** voided runs with no install. These are batch 5 run 26, batch 9 attempt 2 run 57,
  and loop9c run 16. Run 16 is verified not to have rebooted the board.

| scope | installs | resets | rate (exact 95% CI) |
|---|---|---|---|
| all captured installs: run 1 and 2, batches 1–9, batch-8 baseline + hand retry + bootstrap, batch 9 attempt 1 run 1 | **308** | **8** (resets 1–8) | **2.6% (1.1–5.1%)** |
| under the soft-lockup detector (batch 8 + batch 9, all attempts) | 79 | 2 (resets 7, 8) | 2.5% (0.3–8.9%) |
| at `watchdog_thresh=1` (batch 9 attempts 1–3) | 73 | 1 (reset 8) | 1.4% (0.03–7.4%) |

- **Counting caveats.** The batch-8 hand retry is counted from the README text only. Batch 9
  attempt 1 run 1 was a real, clean install, but the README excludes it from run totals. Without
  those two installs the main row is 8/306, still 2.6%.
- **Which resets carried which instruments:**
  - reset 1 had no `[stats]`;
  - resets 2–4 had `[stats]`;
  - resets 5, 7 and 8 had the wdt/PID1 heartbeat (reset 6 had none armed);
  - resets 7 and 8 had the detector.
- **Rates.**
  - The rate has not moved across elevator, governor, detector or threshold changes: BFQ 1/85 and
    the detector-era 2/79 against 3/114 default.
  - Loop9c's next 17 runs would expect ~0.4 resets at 2.6%.
  - Zero false soft-lockup panics in 73 thresh=1 installs, with install-window load up to 9.51.

## Classes and revert

- **Board changes: none, so there is nothing to revert.**
  - The three sessions ran only `cat` of /proc and /sys, `hexdump` of /proc/device-tree, `dmesg`,
    `journalctl`, `ps`, `ls`/`find`/`readlink` of /lib/modules and /sys, `rauc status`,
    `fw_printenv`, `systemctl show`/`cat`/`list-timers`, and `uname`/`date`.
  - pstore was not mounted, and nothing was deleted.
- **Host side**, I wrote only `scratchpad/reset8/*` and this file.

## Measurement notes

- **Board sessions:** 3, all read-only. RSTS was read once (n = 1 this reset; 7 of 7 across resets
  2–8).
- **K:** 20 host-stamped uptime samples, using the minimum-latency estimator, cross-checked against
  the dmesg head (Δ −4 ms).
- **F:** n = 18 warm reboots, 7.32–7.43 s. The shutdown tail is unmeasured, and only B ≤ F is used.
- **Healthy comparison:** loop9c runs 1–15 (same sha `3bd3e8a9`, board, loop and thresh=1). They are
  compared with run 17 and never pooled with it.
- **Verified in source (6.12.93 work-shared tree):**
  - the softlockup sample period, units and report condition (re-read for thresh=1);
  - the HARD hrtimer mode;
  - printk legacy deferral under `printk_cpu_sync`;
  - the bcm2835.c 10 s delayed-work timeout and its message;
  - the `bcm2835-sdhost.c` PIO loop (not built);
  - the pstore ftrace record layout (seq counter);
  - the ramoops DT parse (`ftrace-size` defaults to 0);
  - the rpi ramoops overlay's override list.
- **Verified on the board:** mmc0 is bound to `sdhost-bcm2835` (bcm2835.c); the soak timer
  definition and its start times.
- **Not verified:**
  - that the detector fires on this board (detection never seeded);
  - the panic print and dump time;
  - the watchdog tick scale (k ∈ [1.00, 1.08] carried; k ≥ 1.02 fits exactly, k = 1 misses by
    0.10 s);
  - the JTAG halt behaviour under a bus stall;
  - the pstore ftrace overhead on this board.
- **Model inputs:** S uniform in its window; dump time assumed (0–5 s). The P values in §3 are
  model outputs, not measurements.
